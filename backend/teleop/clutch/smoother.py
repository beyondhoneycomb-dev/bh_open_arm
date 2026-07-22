"""One Euro pose smoother: adaptive-cutoff position, SLERP rotation (`FR-TEL-039`/`040`).

The One Euro filter trades lag against jitter with a cutoff that rises with speed, so a
still pose is smoothed hard while a fast pose barely lags. Position runs three scalar
filters (one per axis); rotation runs the same adaptive law over the angular speed and
applies the resulting factor through SLERP.

`reset()` is the safety-relevant method (`FR-TEL-040`): it clears all filter state so
the next `filter()` call passes its input through untouched. It MUST be called when
tracking validity returns from INVALID and when the clutch re-engages — without it the
stale previous sample and derivative estimate inject a transient at exactly the moment
the pose has jumped, which is the re-entry jump the WebXR path shipped (`05` §2.7 ⓔ).
The coordinator that decides those two moments is `conditioner.py`.
"""

from __future__ import annotations

import math

import numpy as np

from backend.teleop.clutch.constants import (
    BETA_DEFAULT,
    BETA_MAX,
    BETA_MIN,
    D_CUTOFF_DEFAULT,
    D_CUTOFF_MAX,
    D_CUTOFF_MIN,
    LOOP_FPS_DEFAULT,
    MIN_CUTOFF_DEFAULT,
    MIN_CUTOFF_MAX,
    MIN_CUTOFF_MIN,
)
from backend.teleop.clutch.rotation import angle_between, quat_normalize, slerp
from backend.teleop.clutch.scale import PoseTarget

# The fallback timestep used only for the first sample after a reset, where no prior
# time exists to difference against. It is the nominal loop period; a real dt replaces
# it on every subsequent sample.
_DEFAULT_DT_S = 1.0 / LOOP_FPS_DEFAULT


def _smoothing_alpha(dt: float, cutoff: float) -> float:
    """Return the exponential-smoothing factor for a cutoff frequency and timestep.

    Args:
        dt: Timestep in seconds (> 0).
        cutoff: Cutoff frequency in Hz (> 0).

    Returns:
        (float) The factor `alpha` in `(0, 1]` for `alpha*new + (1-alpha)*prev`.
    """
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class _ScalarOneEuro:
    """A single-channel One Euro filter with resettable state.

    Not part of the public surface: the pose smoother owns three of these for position.
    """

    def __init__(self, min_cutoff: float, beta: float, d_cutoff: float) -> None:
        """Store the tuning and start uninitialised."""
        self._min_cutoff = min_cutoff
        self._beta = beta
        self._d_cutoff = d_cutoff
        self._value_prev: float | None = None
        self._deriv_prev = 0.0

    def reset(self) -> None:
        """Drop all state so the next `filter` returns its input unchanged."""
        self._value_prev = None
        self._deriv_prev = 0.0

    def filter(self, value: float, dt: float) -> float:
        """Filter one sample.

        Args:
            value: The raw sample.
            dt: Seconds since the previous sample (> 0).

        Returns:
            (float) The smoothed sample; equal to `value` on the first call after a reset.
        """
        if self._value_prev is None:
            self._value_prev = value
            self._deriv_prev = 0.0
            return value
        deriv = (value - self._value_prev) / dt
        deriv_hat = self._deriv_prev + _smoothing_alpha(dt, self._d_cutoff) * (
            deriv - self._deriv_prev
        )
        cutoff = self._min_cutoff + self._beta * abs(deriv_hat)
        value_hat = self._value_prev + _smoothing_alpha(dt, cutoff) * (value - self._value_prev)
        self._value_prev = value_hat
        self._deriv_prev = deriv_hat
        return value_hat


class OneEuroPoseSmoother:
    """One Euro smoothing of a 6-DoF pose: per-axis position and SLERP rotation.

    One instance serves one arm on the loop thread. `filter` advances the state; `reset`
    clears it. `is_initialized` reports whether a first post-reset sample has been seen —
    used by tests and by the coordinator to assert the reset actually took effect.
    """

    def __init__(
        self,
        min_cutoff: float = MIN_CUTOFF_DEFAULT,
        beta: float = BETA_DEFAULT,
        d_cutoff: float = D_CUTOFF_DEFAULT,
    ) -> None:
        """Create a smoother from the One Euro tuning triple.

        Args:
            min_cutoff: Floor cutoff frequency in Hz (`FR-TEL-039`, default 2.0).
            beta: Speed coefficient raising the cutoff with motion (default 0.04).
            d_cutoff: Cutoff of the derivative filter in Hz (default 1.5).

        Raises:
            ValueError: If any parameter is outside its adjustable range.
        """
        if not MIN_CUTOFF_MIN <= min_cutoff <= MIN_CUTOFF_MAX:
            raise ValueError(
                f"min_cutoff {min_cutoff} outside [{MIN_CUTOFF_MIN}, {MIN_CUTOFF_MAX}]"
            )
        if not BETA_MIN <= beta <= BETA_MAX:
            raise ValueError(f"beta {beta} outside [{BETA_MIN}, {BETA_MAX}]")
        if not D_CUTOFF_MIN <= d_cutoff <= D_CUTOFF_MAX:
            raise ValueError(f"d_cutoff {d_cutoff} outside [{D_CUTOFF_MIN}, {D_CUTOFF_MAX}]")
        self._min_cutoff = min_cutoff
        self._beta = beta
        self._d_cutoff = d_cutoff
        self._axes = [_ScalarOneEuro(min_cutoff, beta, d_cutoff) for _ in range(3)]
        self._rot_speed = _ScalarOneEuro(min_cutoff, beta, d_cutoff)
        self._quat_prev: np.ndarray | None = None
        self._time_prev: float | None = None

    @property
    def is_initialized(self) -> bool:
        """Whether a sample has been filtered since construction or the last reset."""
        return self._time_prev is not None

    def reset(self) -> None:
        """Clear all position, rotation and timing state (`FR-TEL-040`).

        After this the next `filter` call returns its input pose unchanged, so no stale
        sample or derivative can leak across an INVALID gap or a clutch re-grip.
        """
        for axis in self._axes:
            axis.reset()
        self._rot_speed.reset()
        self._quat_prev = None
        self._time_prev = None

    def filter(self, position: np.ndarray, quaternion: np.ndarray, timestamp: float) -> PoseTarget:
        """Smooth one pose sample.

        Args:
            position: Raw target position `(x, y, z)`.
            quaternion: Raw target orientation `(x, y, z, w)`.
            timestamp: Monotonic sample time in seconds (the server receive instant).

        Returns:
            (PoseTarget) The smoothed pose; equal to the input on the first call after a
            reset (pass-through), so a re-entry never injects a transient.
        """
        raw_quat = quat_normalize(quaternion)
        if self._time_prev is None:
            dt = _DEFAULT_DT_S
        else:
            dt = timestamp - self._time_prev
            if dt <= 0.0:
                dt = _DEFAULT_DT_S

        smoothed_position = np.array(
            [self._axes[i].filter(float(position[i]), dt) for i in range(3)]
        )

        if self._quat_prev is None:
            smoothed_quat = raw_quat
        else:
            angular_speed = angle_between(raw_quat, self._quat_prev) / dt
            speed_hat = self._rot_speed.filter(angular_speed, dt)
            cutoff = self._min_cutoff + self._beta * abs(speed_hat)
            smoothed_quat = slerp(self._quat_prev, raw_quat, _smoothing_alpha(dt, cutoff))

        self._quat_prev = smoothed_quat
        self._time_prev = timestamp
        return PoseTarget(position=smoothed_position, quaternion=smoothed_quat)
