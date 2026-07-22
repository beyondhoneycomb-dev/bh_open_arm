"""The WebXR pose source: per-arm samples over a resolved session (WP-3B-08).

This binds the session, the profile resolution and the gamepad reads into one
per-arm sample carrying the grip pose, the clutch/stick/face inputs, and the shared
`CTR-TEL@v1` validity and dual timestamps. It is the WebXR counterpart of the UDP
receiver (`WP-3B-07`); both sit behind the same `PoseSource` idea so the
teleoperator body downstream (`WP-3B-09`/`10`) is source-agnostic (`05` §2.7).

`frame_applied` is `True` and declared as data: the WebXR receiver already emits
world-frame poses (`05` §2.8), so the single coordinate transform happens upstream
and this source must not re-apply `R_ROBOT`. Declaring it lets the double-transform
guard be a static check, not a runtime hope (`FR-TEL-008`).

Two contract facts are consumed, not restated (`02b` §5.0b): the tracking validity
is the frozen three-level `OK`/`STALE`/`INVALID` model, and the source `t` (CLIENT
clock, an age input) and the PC receive instant (SERVER `CLOCK_MONOTONIC`) are both
preserved (`FR-TEL-021`/`022`). WebXR has no native validity signal, so this source
maps a present grip pose to `OK` and a lost one (getPose returned null) to `INVALID`;
`STALE` is a heartbeat-age verdict stamped by the safety layer (`WP-3B-10`), never
fabricated here.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.teleop.webxr.gamepad import (
    FaceButtons,
    GamepadState,
    Thumbstick,
    read_face_buttons,
    read_squeeze,
    read_thumbstick,
    read_trigger,
)
from backend.teleop.webxr.session import Handedness, ImmersiveArSession, TeleopMode
from contracts.teleop import TeleopSample, TeleopValidity


@dataclass(frozen=True)
class GripPose:
    """A controller grip pose, already in the robot world frame.

    The orientation is scalar-first `[qw, qx, qy, qz]` (`FR-TEL-025`). The pose is
    world-frame because the WebXR receiver applied the transform upstream; this type
    carries no flag of its own, since `WebXrPoseSource.frame_applied` declares it once
    for the whole source.

    Attributes:
        position: The `(x, y, z)` position in metres, robot world frame.
        orientation: The `(qw, qx, qy, qz)` orientation quaternion, scalar-first.
    """

    position: tuple[float, float, float]
    orientation: tuple[float, float, float, float]


@dataclass(frozen=True)
class WebXrArmSample:
    """One arm's WebXR sample: pose, inputs, validity and both timestamps.

    Attributes:
        handedness: The arm this sample is for.
        grip_pose: The world-frame grip pose, or None when tracking is lost.
        squeeze: The `buttons[1]` squeeze analog value (the clutch input).
        trigger: The `buttons[0]` trigger analog value.
        thumbstick: The `axes[2]/[3]` thumbstick reading, or None when the axis-count
            guard fails (fewer than four axes).
        face_buttons: The A/X and B/Y analog readings.
        teleop_sample: The frozen `CTR-TEL@v1` sample — validity and dual timestamps.
    """

    handedness: Handedness
    grip_pose: GripPose | None
    squeeze: float
    trigger: float
    thumbstick: Thumbstick | None
    face_buttons: FaceButtons
    teleop_sample: TeleopSample

    @property
    def validity(self) -> TeleopValidity:
        """The tracking validity of this sample (OK or INVALID for the WebXR source)."""
        return self.teleop_sample.validity


class WebXrPoseSource:
    """A WebXR pose source over a begun immersive-ar session.

    `read` consumes one already-world-frame grip pose and one gamepad sample for an
    active arm and returns the assembled `WebXrArmSample`, caching it so `latest` is a
    non-blocking snapshot read (`FR-TEL-005`: the action read never blocks). Reading an
    inactive arm, or reading before the session begins, is rejected by the session.
    """

    # The WebXR receiver applies the single world-frame transform upstream (`05` §2.8),
    # so this source declares the transform already applied and never re-applies it.
    # Static, not per-instance: it is a property of the WebXR path, not of a session.
    frame_applied = True

    def __init__(self, session: ImmersiveArSession) -> None:
        self._session = session
        self._latest: dict[Handedness, WebXrArmSample] = {}

    @property
    def session(self) -> ImmersiveArSession:
        """The session this source reads over."""
        return self._session

    @property
    def mode(self) -> TeleopMode:
        """The teleop mode (single-arm or bimanual) of the underlying session."""
        return self._session.config.mode

    def read(
        self,
        handedness: Handedness,
        grip_pose: GripPose | None,
        gamepad: GamepadState,
        source_ts: float,
        receive_mono_ns: int,
    ) -> WebXrArmSample:
        """Assemble and cache one arm's sample.

        Args:
            handedness: The arm to read; must be active in the session's mode.
            grip_pose: The world-frame grip pose, or None when tracking is lost.
            gamepad: The controller gamepad sampled this frame.
            source_ts: The headset source time (`t`), CLIENT clock, an age input.
            receive_mono_ns: The PC receive instant, SERVER `CLOCK_MONOTONIC` ns.

        Returns:
            (WebXrArmSample) The assembled sample, also stored as this arm's latest.

        Raises:
            SessionError: If the session has not begun or the arm is not active.
        """
        layout = self._session.resolution_for(handedness).layout
        validity = TeleopValidity.OK if grip_pose is not None else TeleopValidity.INVALID
        sample = WebXrArmSample(
            handedness=handedness,
            grip_pose=grip_pose,
            squeeze=read_squeeze(gamepad, layout),
            trigger=read_trigger(gamepad, layout),
            thumbstick=read_thumbstick(gamepad, layout),
            face_buttons=read_face_buttons(gamepad, layout),
            teleop_sample=TeleopSample(
                source_ts=source_ts, receive_mono_ns=receive_mono_ns, validity=validity
            ),
        )
        self._latest[handedness] = sample
        return sample

    def latest(self, handedness: Handedness) -> WebXrArmSample | None:
        """Return this arm's most recent sample without blocking.

        Args:
            handedness: The arm to read.

        Returns:
            (WebXrArmSample | None) The last sample read for this arm, or None.
        """
        return self._latest.get(handedness)
