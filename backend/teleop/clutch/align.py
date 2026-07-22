"""The alignment ramp — a per-second rate, never a per-frame constant (`FR-TEL-083`).

Before following resumes (state S2->S3->S4, `05` §4.1) the commanded joint vector ramps
from the held pose toward the IK target so the follower does not snap. The ramp rate is
`align_rate_rad_s` (rad/second); the per-frame step is DERIVED as `align_rate_rad_s /
fps`, so the achieved rate is the same 0.5 rad/s at 60 Hz, 500 Hz or any loop rate.

Encoding a per-frame constant (rad/event) instead is the defect this module exists to
prevent: the upstream `0.001 rad/event` was tuned at 500 Hz (= 0.5 rad/s), and reused
unchanged at 60 Hz it collapses to 0.06 rad/s — an order of magnitude slower, scaling
with the frame-rate ratio. `step_size(fps)` is the single place the derivation lives.
"""

from __future__ import annotations

import numpy as np

from backend.teleop.clutch.constants import (
    ALIGN_RATE_RAD_S_DEFAULT,
    ALIGN_RATE_RAD_S_MAX,
    ALIGN_RATE_RAD_S_MIN,
    ALIGN_THRESHOLD_RAD_DEFAULT,
    ALIGN_THRESHOLD_RAD_MAX,
    ALIGN_THRESHOLD_RAD_MIN,
    LOOP_FPS_DEFAULT,
)


class AlignRamp:
    """Rate-limits a joint vector toward a target at a fixed rad/second rate.

    Stateless across ticks: the caller holds the ramping vector and passes it back each
    frame, so one instance serves either arm. The rate and the convergence band are the
    only configuration.
    """

    def __init__(
        self,
        align_rate_rad_s: float = ALIGN_RATE_RAD_S_DEFAULT,
        align_threshold_rad: float = ALIGN_THRESHOLD_RAD_DEFAULT,
    ) -> None:
        """Create a ramp from a per-second rate and a convergence band.

        Args:
            align_rate_rad_s: Ramp rate in rad/second (`FR-TEL-083`, default 0.5). This
                is a rate, not a per-frame step; the step is derived per frame.
            align_threshold_rad: Per-joint band within which alignment is converged.

        Raises:
            ValueError: If either value is outside its adjustable range.
        """
        if not ALIGN_RATE_RAD_S_MIN <= align_rate_rad_s <= ALIGN_RATE_RAD_S_MAX:
            raise ValueError(
                f"align_rate_rad_s {align_rate_rad_s} outside "
                f"[{ALIGN_RATE_RAD_S_MIN}, {ALIGN_RATE_RAD_S_MAX}]"
            )
        if not ALIGN_THRESHOLD_RAD_MIN <= align_threshold_rad <= ALIGN_THRESHOLD_RAD_MAX:
            raise ValueError(
                f"align_threshold_rad {align_threshold_rad} outside "
                f"[{ALIGN_THRESHOLD_RAD_MIN}, {ALIGN_THRESHOLD_RAD_MAX}]"
            )
        self._align_rate_rad_s = align_rate_rad_s
        self._align_threshold_rad = align_threshold_rad

    @property
    def align_rate_rad_s(self) -> float:
        """The ramp rate in rad/second."""
        return self._align_rate_rad_s

    @property
    def align_threshold_rad(self) -> float:
        """The per-joint convergence band in radians."""
        return self._align_threshold_rad

    def step_size(self, fps: int = LOOP_FPS_DEFAULT) -> float:
        """Return the per-frame step in radians, derived from the rate and loop rate.

        This is the whole point of the module: `align_rate_rad_s / fps`, so the achieved
        rate is independent of `fps`. It is never a stored per-frame constant.

        Args:
            fps: The teleop loop rate in Hz (> 0).

        Returns:
            (float) The maximum per-joint change this frame, in radians.

        Raises:
            ValueError: If `fps` is not positive.
        """
        if fps <= 0:
            raise ValueError(f"fps must be positive, got {fps}")
        return self._align_rate_rad_s / fps

    def step(
        self, current: np.ndarray, target: np.ndarray, fps: int = LOOP_FPS_DEFAULT
    ) -> np.ndarray:
        """Advance `current` toward `target` by at most one frame's rate-limited step.

        Args:
            current: The joint vector being ramped (radians).
            target: The IK target joint vector (radians).
            fps: The teleop loop rate in Hz.

        Returns:
            (np.ndarray) The next joint vector, each element clipped to the per-frame step.
        """
        max_step = self.step_size(fps)
        delta = np.asarray(target, dtype=float) - np.asarray(current, dtype=float)
        clipped = np.clip(delta, -max_step, max_step)
        return np.asarray(current, dtype=float) + clipped

    def is_converged(self, current: np.ndarray, target: np.ndarray) -> bool:
        """Report whether every joint is within the convergence band of the target.

        Args:
            current: The ramping joint vector (radians).
            target: The target joint vector (radians).

        Returns:
            (bool) True when `max |target - current| < align_threshold_rad`.
        """
        delta = np.asarray(target, dtype=float) - np.asarray(current, dtype=float)
        return bool(np.all(np.abs(delta) < self._align_threshold_rad))
