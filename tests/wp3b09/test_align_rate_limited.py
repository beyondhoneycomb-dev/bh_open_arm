"""RUNS ④ (CG-3B-09c) — the align ramp is a per-second rate, not a per-frame constant.

`FR-TEL-083`: the per-frame step is derived as `align_rate_rad_s / fps`, so the achieved
rate is fps-invariant. Encoding the upstream `0.001 rad/event` constant instead — tuned
at 500 Hz — collapses to `0.06 rad/s` at 60 Hz. The exact slowdown is the frame-rate
ratio 500/60 (~8.3x; the spec rounds it to "an order of magnitude / 12x"); this test
reproduces both the invariance and the defect.
"""

from __future__ import annotations

import numpy as np

from backend.teleop.clutch import AlignRamp
from backend.teleop.clutch.constants import ALIGN_RATE_RAD_S_DEFAULT

# The upstream dora per-event step and the loop it was tuned at (05 §3 align row):
# 0.001 rad/event x 500 Hz = 0.5 rad/s. Reused unchanged at 60 Hz it is the defect.
_UPSTREAM_STEP_RAD_PER_EVENT = 0.001
_UPSTREAM_LOOP_HZ = 500
_LOOP_HZ_60 = 60
_ONE_SECOND_OF_FRAMES_60 = 60


def _ramp_displacement(ramp: AlignRamp, fps: int, frames: int) -> float:
    """Ramp a single joint from 0 toward a far target and return the distance covered."""
    current = np.zeros(1)
    target = np.array([10.0])  # far enough never to converge within the window
    for _ in range(frames):
        current = ramp.step(current, target, fps)
    return float(current[0])


def test_step_size_is_rate_over_fps() -> None:
    """The per-frame step is exactly `align_rate_rad_s / fps`, at any loop rate."""
    ramp = AlignRamp()
    assert ramp.step_size(60) == ALIGN_RATE_RAD_S_DEFAULT / 60
    assert ramp.step_size(500) == ALIGN_RATE_RAD_S_DEFAULT / 500


def test_effective_rate_is_fps_invariant() -> None:
    """One second of ramping covers the same distance at 60 Hz and 500 Hz."""
    ramp = AlignRamp()
    covered_60 = _ramp_displacement(ramp, 60, 60)
    covered_500 = _ramp_displacement(ramp, 500, 500)
    assert np.isclose(covered_60, ALIGN_RATE_RAD_S_DEFAULT)
    assert np.isclose(covered_500, ALIGN_RATE_RAD_S_DEFAULT)
    assert np.isclose(covered_60, covered_500)


def test_per_frame_constant_is_slower_by_the_frame_rate_ratio() -> None:
    """A stored per-frame constant makes alignment fps-dependent and far slower at 60 Hz."""
    ramp = AlignRamp()
    rate_based_per_second = _ramp_displacement(ramp, _LOOP_HZ_60, _ONE_SECOND_OF_FRAMES_60)

    # The defect: the same 0.001 rad/event applied per frame, ignoring the loop rate.
    per_frame_constant_per_second = _UPSTREAM_STEP_RAD_PER_EVENT * _ONE_SECOND_OF_FRAMES_60

    assert np.isclose(rate_based_per_second, ALIGN_RATE_RAD_S_DEFAULT)  # 0.5 rad/s
    assert np.isclose(per_frame_constant_per_second, 0.06)  # 0.001 x 60

    slowdown = rate_based_per_second / per_frame_constant_per_second
    assert np.isclose(slowdown, _UPSTREAM_LOOP_HZ / _LOOP_HZ_60)  # exactly 500/60
    assert slowdown > 8.0  # an order of magnitude slower — the FAIL_BLOCKING branch


def test_convergence_band() -> None:
    """Convergence is per-joint within the threshold band."""
    ramp = AlignRamp(align_threshold_rad=0.1)
    current = np.array([0.0, 0.0, 0.0])
    assert ramp.is_converged(current, np.array([0.05, -0.05, 0.09])) is True
    assert ramp.is_converged(current, np.array([0.05, -0.05, 0.20])) is False
