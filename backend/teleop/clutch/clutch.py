"""The clutch (deadman) gate and its pose reference latch (`FR-TEL-030`/`031`).

The follower tracks the leader only while the squeeze analog is at or above the deadman
threshold. The invariant this module exists to guarantee is the re-grip one: releasing
the clutch DISCARDS the reference (controller pose + EE pose captured at grip), and
re-gripping RE-CAPTURES it, so the relative delta at the instant of re-grip is exactly
zero and the follower does not jump (`FR-TEL-031`, `05` §4.2 forbidden transition 7).

The gate is a per-arm object driven one sample at a time; it holds no thread and no
timing. Sanity of the incoming pose (non-finite, degenerate) is the safety gate's
concern (`WP-3B-10`), so the reference is captured as given.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.teleop.clutch.constants import (
    DEADMAN_THRESHOLD_DEFAULT,
    DEADMAN_THRESHOLD_MAX,
    DEADMAN_THRESHOLD_MIN,
)


@dataclass(frozen=True, eq=False)
class PoseReference:
    """The pose pair latched at the instant the clutch engaged.

    A delta is measured against `controller_*`; the scaled delta is applied on top of
    `ee_*`. Re-capturing both at re-grip is what forces the delta to start at zero.

    Attributes:
        controller_position: Leader controller position `(x, y, z)` at grip.
        controller_quaternion: Leader controller orientation `(x, y, z, w)` at grip.
        ee_position: Follower end-effector position `(x, y, z)` at grip.
        ee_quaternion: Follower end-effector orientation `(x, y, z, w)` at grip.
    """

    controller_position: np.ndarray
    controller_quaternion: np.ndarray
    ee_position: np.ndarray
    ee_quaternion: np.ndarray


@dataclass(frozen=True)
class ClutchEvent:
    """What one `ClutchGate.update` transition did.

    Attributes:
        engaged: Whether the clutch is engaged after this sample.
        just_engaged: True on the rising edge — the reference was re-captured this tick,
            so a consumer must reset any smoother to avoid a re-entry transient.
        just_released: True on the falling edge — the reference was discarded this tick.
    """

    engaged: bool
    just_engaged: bool
    just_released: bool


class ClutchGate:
    """A per-arm deadman gate that latches and discards the pose reference.

    One instance serves one arm on the teleop loop thread. `update` is the only mutator;
    `is_engaged` and `reference` read the latched state between ticks.
    """

    def __init__(self, threshold: float = DEADMAN_THRESHOLD_DEFAULT) -> None:
        """Create a gate at a grip threshold.

        Args:
            threshold: Grip value at or above which the clutch engages. Must lie in the
                adjustable deadman range (`05` §3 clutch row).

        Raises:
            ValueError: If `threshold` is outside `[DEADMAN_THRESHOLD_MIN,
                DEADMAN_THRESHOLD_MAX]`.
        """
        if not DEADMAN_THRESHOLD_MIN <= threshold <= DEADMAN_THRESHOLD_MAX:
            raise ValueError(
                f"deadman threshold {threshold} outside "
                f"[{DEADMAN_THRESHOLD_MIN}, {DEADMAN_THRESHOLD_MAX}]"
            )
        self._threshold = threshold
        self._engaged = False
        self._reference: PoseReference | None = None

    @property
    def threshold(self) -> float:
        """The grip value at or above which this gate engages."""
        return self._threshold

    @property
    def is_engaged(self) -> bool:
        """Whether the clutch is currently engaged."""
        return self._engaged

    @property
    def reference(self) -> PoseReference | None:
        """The latched reference while engaged, or None once released."""
        return self._reference

    def update(
        self,
        grip: float,
        controller_position: np.ndarray,
        controller_quaternion: np.ndarray,
        ee_position: np.ndarray,
        ee_quaternion: np.ndarray,
    ) -> ClutchEvent:
        """Drive the gate with one sample and report the transition.

        On the rising edge the reference is captured from the arguments; on the falling
        edge it is discarded. Passing the current EE pose every tick lets the gate latch
        the follower pose that the delta will be applied on top of.

        Args:
            grip: The squeeze analog for this arm, in `[0, 1]`.
            controller_position: Leader controller position `(x, y, z)`.
            controller_quaternion: Leader controller orientation `(x, y, z, w)`.
            ee_position: Current follower EE position `(x, y, z)`.
            ee_quaternion: Current follower EE orientation `(x, y, z, w)`.

        Returns:
            (ClutchEvent) The post-update engagement state and edge flags.
        """
        engaged_now = grip >= self._threshold
        just_engaged = engaged_now and not self._engaged
        just_released = not engaged_now and self._engaged

        if just_engaged:
            self._reference = PoseReference(
                controller_position=np.asarray(controller_position, dtype=float),
                controller_quaternion=np.asarray(controller_quaternion, dtype=float),
                ee_position=np.asarray(ee_position, dtype=float),
                ee_quaternion=np.asarray(ee_quaternion, dtype=float),
            )
        elif just_released:
            self._reference = None

        self._engaged = engaged_now
        return ClutchEvent(
            engaged=engaged_now, just_engaged=just_engaged, just_released=just_released
        )
