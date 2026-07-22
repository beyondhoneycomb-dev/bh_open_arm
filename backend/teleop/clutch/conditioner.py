"""Per-arm pose conditioning that enforces the smoother-reset invariant (`FR-TEL-040`).

This is the seam between the VR source (`WP-3B-07`/`08`) and the safety state machine
(`WP-3B-10`). It consumes the source-agnostic `PoseSource` / `VrFrame` interface from
`backend.teleop.vr_udp` by import — the same frame whether poses arrive over UDP or
WebXR — and never re-implements reception or the coordinate transform (`02b` §5.0b, "do
not duplicate"). `VrFrame` already carries the `R_ROBOT` world-frame transform
(`frame_applied`); this layer applies only the clutch, scale and smoother on top.

It drives the clutch, maps the scaled delta and smooths the result, and — the reason it
exists as one object — it is the single place that decides WHEN
`OneEuroPoseSmoother.reset()` fires:

- when an arm's tracking validity returns from INVALID to a publishable level, and
- when the clutch re-engages (grip rising edge).

Both moments carry a pose discontinuity, so a missed reset is a re-entry jump
(`FR-TEL-040`, the `FAIL_BLOCKING` branch). Every `process` call reports whether a reset
fired, so the invariant is observable and testable rather than buried in control flow.

The state machine that consumes this (`WP-3B-10`) still owns the ALIGNING ramp on the
joint command and the heartbeat; on an INVALID arm this conditioner withholds the pose
(the source already dropped `world_pose`) and resets nothing until validity recovers,
matching `05` §2.7 (STALE still passes through; INVALID withholds).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.teleop.clutch.clutch import ClutchGate
from backend.teleop.clutch.constants import NANOS_PER_SECOND
from backend.teleop.clutch.scale import DeltaScaler, PoseTarget
from backend.teleop.clutch.smoother import OneEuroPoseSmoother
from backend.teleop.vr_udp.frame import VrFrame
from backend.teleop.vr_udp.source import PoseSource
from backend.teleop.vr_udp.transform import WorldPose
from contracts.teleop import TeleopValidity


def _world_pose_to_position_quat(world_pose: WorldPose) -> tuple[np.ndarray, np.ndarray]:
    """Split a source `WorldPose` into a position and a scalar-last quaternion.

    `WorldPose` is `[px, py, pz, qw, qx, qy, qz]`, scalar-FIRST (`WP-3B-07` `05` §2.8).
    This module works scalar-LAST `(x, y, z, w)` throughout (matching `CTR-TEL@v1`'s wire
    order), so the one convention change happens here, at the source boundary, once.

    Args:
        world_pose: The transformed EE target from the VR source.

    Returns:
        (tuple[np.ndarray, np.ndarray]) The `(x, y, z)` position and `(x, y, z, w)` quat.
    """
    px, py, pz, qw, qx, qy, qz = world_pose
    return np.array([px, py, pz]), np.array([qx, qy, qz, qw])


class ValidityTracker:
    """Detects the INVALID -> valid edge across successive samples.

    One instance per arm. `update` records the current validity and reports only the
    transition that requires a smoother reset — INVALID followed by any publishable
    level (OK or STALE).
    """

    def __init__(self) -> None:
        """Start with no prior validity, so the first sample is never an edge."""
        self._prev: TeleopValidity | None = None

    def update(self, validity: TeleopValidity) -> bool:
        """Record `validity` and report whether this is an INVALID -> valid transition.

        Args:
            validity: The tracking validity of the current sample.

        Returns:
            (bool) True when the previous sample was INVALID and this one is publishable.
        """
        was_invalid = self._prev is TeleopValidity.INVALID
        self._prev = validity
        return was_invalid and validity.is_publishable


@dataclass(frozen=True)
class ConditionResult:
    """The outcome of conditioning one VR frame for one arm.

    Attributes:
        engaged: Whether the clutch is engaged after this sample.
        published: Whether a pose was published (False when the arm was INVALID).
        target: The smoothed EE target when engaged and published, else None.
        smoother_reset: Whether `reset()` fired this tick — the `FR-TEL-040` observable.
        reference_captured: Whether the clutch reference was (re)captured this tick.
    """

    engaged: bool
    published: bool
    target: PoseTarget | None
    smoother_reset: bool
    reference_captured: bool


class TeleopPoseConditioner:
    """Clutch + scale + smoother for one arm, wired to enforce the reset invariant.

    Owns one `ClutchGate`, `DeltaScaler`, `OneEuroPoseSmoother` and `ValidityTracker`,
    all on the loop thread. `process` conditions a `VrFrame` for one arm; `process_source`
    pulls the latest frame from a `PoseSource` first. The components are exposed read-only
    so a GUI can show clutch state and scale factors.
    """

    def __init__(
        self,
        clutch: ClutchGate | None = None,
        scaler: DeltaScaler | None = None,
        smoother: OneEuroPoseSmoother | None = None,
    ) -> None:
        """Assemble the per-arm conditioner from its components (defaults when omitted).

        Args:
            clutch: The deadman gate; a default-threshold gate when None.
            scaler: The delta scaler; default position/rotation scale when None.
            smoother: The One Euro smoother; default tuning when None.
        """
        self._clutch = clutch if clutch is not None else ClutchGate()
        self._scaler = scaler if scaler is not None else DeltaScaler()
        self._smoother = smoother if smoother is not None else OneEuroPoseSmoother()
        self._validity = ValidityTracker()

    @property
    def clutch(self) -> ClutchGate:
        """The deadman gate."""
        return self._clutch

    @property
    def scaler(self) -> DeltaScaler:
        """The delta scaler."""
        return self._scaler

    @property
    def smoother(self) -> OneEuroPoseSmoother:
        """The One Euro pose smoother."""
        return self._smoother

    def process_source(
        self,
        source: PoseSource,
        side: str,
        ee_position: np.ndarray,
        ee_quaternion: np.ndarray,
    ) -> ConditionResult | None:
        """Pull the latest frame from a pose source and condition it, or None if none yet.

        `read_latest()` is non-blocking (`WP-3B-07`), so this is safe to call once per
        control tick.

        Args:
            source: The VR pose source (`WP-3B-07`/`08` `PoseSource`).
            side: Which arm this conditioner serves (`"left"` or `"right"`).
            ee_position: Current follower EE position `(x, y, z)` for the reference latch.
            ee_quaternion: Current follower EE orientation `(x, y, z, w)`.

        Returns:
            (ConditionResult | None) The conditioning outcome, or None when no frame has
            arrived from the source yet.
        """
        frame = source.read_latest()
        if frame is None:
            return None
        return self.process(frame, side, ee_position, ee_quaternion)

    def process(
        self,
        frame: VrFrame,
        side: str,
        ee_position: np.ndarray,
        ee_quaternion: np.ndarray,
    ) -> ConditionResult:
        """Condition one VR frame for one arm and report the reset invariant.

        Args:
            frame: The VR source frame (`WP-3B-07`/`08` interface).
            side: Which arm this conditioner serves (`"left"` or `"right"`).
            ee_position: Current follower EE position `(x, y, z)` for the reference latch.
            ee_quaternion: Current follower EE orientation `(x, y, z, w)`.

        Returns:
            (ConditionResult) The engagement state, smoothed target (if any) and whether
            a smoother reset fired this tick.
        """
        arm = frame.arm(side)
        smoother_reset = self._validity.update(arm.validity)

        # An INVALID arm withholds its pose at the source (`world_pose is None`), so it
        # never latches a clutch reference or feeds the smoother. The reset for the gap
        # fires on the recovery edge above, not here (05 §2.7 / FR-TEL-040).
        if not arm.is_publishable or arm.world_pose is None:
            return ConditionResult(
                engaged=self._clutch.is_engaged,
                published=False,
                target=None,
                smoother_reset=False,
                reference_captured=False,
            )

        if smoother_reset:
            self._smoother.reset()

        controller_position, controller_quaternion = _world_pose_to_position_quat(arm.world_pose)
        event = self._clutch.update(
            grip=arm.grip,
            controller_position=controller_position,
            controller_quaternion=controller_quaternion,
            ee_position=ee_position,
            ee_quaternion=ee_quaternion,
        )

        # Re-engage carries a fresh reference, so any stale filter state must go too.
        if event.just_engaged:
            self._smoother.reset()
            smoother_reset = True

        reference = self._clutch.reference
        if not event.engaged or reference is None:
            return ConditionResult(
                engaged=event.engaged,
                published=True,
                target=None,
                smoother_reset=smoother_reset,
                reference_captured=event.just_engaged,
            )

        raw_target = self._scaler.target(reference, controller_position, controller_quaternion)
        timestamp = frame.receive_mono_ns / NANOS_PER_SECOND
        smoothed = self._smoother.filter(raw_target.position, raw_target.quaternion, timestamp)
        return ConditionResult(
            engaged=True,
            published=True,
            target=smoothed,
            smoother_reset=smoother_reset,
            reference_captured=event.just_engaged,
        )
