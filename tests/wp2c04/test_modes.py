"""Threshold evaluation across STATIC / VELOCITY_SCALED / TRAJECTORY_SCHEDULED and the accel term.

The formulas are the FR-SAF-021 contract, so they are checked as exact arithmetic on hand-computed
values, including that the accel term is added live for the two live modes and baked (not double
counted) into the scheduled profile.
"""

from __future__ import annotations

import pytest

from backend.threshold import (
    ThresholdCalibration,
    ThresholdConfig,
    ThresholdConfigError,
    ThresholdMode,
    ThresholdSchedule,
    build_schedule,
    effective_thresholds,
)

_THR0 = ThresholdCalibration.literature_default().thr0
_ZERO = (0.0,) * 7


def _config(
    mode: ThresholdMode,
    *,
    vel_coeff: tuple[float, ...] = (0.05,) * 7,
    acc_coeff: tuple[float, ...] = (0.1,) * 7,
    use_accel_term: bool = False,
) -> ThresholdConfig:
    """A config on the literature base threshold with the given mode and coefficients."""
    return ThresholdConfig(
        calibration=ThresholdCalibration.literature_default(),
        mode=mode,
        vel_coeff=vel_coeff,
        acc_coeff=acc_coeff,
        use_accel_term=use_accel_term,
        confirm_samples=5,
        hysteresis_ratio=0.7,
        per_joint_enable=(True,) * 7,
    )


def test_static_ignores_state() -> None:
    """STATIC returns thr0 regardless of velocity or acceleration."""
    config = _config(ThresholdMode.STATIC)
    fast = (3.0,) * 7
    accel = (10.0,) * 7
    assert effective_thresholds(config, fast, accel) == _THR0


def test_velocity_scaled_adds_velocity_term() -> None:
    """VELOCITY_SCALED adds c_i.|qdot_i| and is insensitive to the sign of velocity."""
    config = _config(ThresholdMode.VELOCITY_SCALED, vel_coeff=(0.05,) * 7)
    qdot = (2.0, -2.0, 2.0, -2.0, 2.0, -2.0, 2.0)
    result = effective_thresholds(config, qdot, _ZERO)
    for joint in range(7):
        assert result[joint] == pytest.approx(_THR0[joint] + 0.05 * 2.0)


def test_accel_term_added_live_for_velocity_scaled() -> None:
    """With the accel term on, VELOCITY_SCALED adds a_i.|qddot_i| on top of the velocity term."""
    config = _config(
        ThresholdMode.VELOCITY_SCALED,
        vel_coeff=(0.05,) * 7,
        acc_coeff=(0.1,) * 7,
        use_accel_term=True,
    )
    qdot = (2.0,) * 7
    qddot = (-3.0,) * 7
    result = effective_thresholds(config, qdot, qddot)
    for joint in range(7):
        assert result[joint] == pytest.approx(_THR0[joint] + 0.05 * 2.0 + 0.1 * 3.0)


def test_accel_term_off_is_inert() -> None:
    """With the accel term off, acc_coeff does not move the threshold."""
    config = _config(ThresholdMode.STATIC, acc_coeff=(0.5,) * 7, use_accel_term=False)
    assert effective_thresholds(config, _ZERO, (9.0,) * 7) == _THR0


def test_trajectory_scheduled_returns_scheduled_vector() -> None:
    """TRAJECTORY_SCHEDULED returns the scheduled vector and ignores the live accel term."""
    config = _config(ThresholdMode.TRAJECTORY_SCHEDULED, acc_coeff=(0.5,) * 7, use_accel_term=True)
    scheduled = tuple(value + 1.0 for value in _THR0)
    # Live qddot is large; a double-counting bug would add a_i.|qddot_i| on top of `scheduled`.
    result = effective_thresholds(config, (1.0,) * 7, (100.0,) * 7, scheduled=scheduled)
    assert result == scheduled


def test_trajectory_scheduled_requires_schedule() -> None:
    """TRAJECTORY_SCHEDULED with no scheduled vector is refused, not silently treated as STATIC."""
    config = _config(ThresholdMode.TRAJECTORY_SCHEDULED)
    with pytest.raises(ThresholdConfigError, match="TRAJECTORY_SCHEDULED requires"):
        effective_thresholds(config, _ZERO, _ZERO)


def test_build_schedule_bakes_velocity_and_accel_from_plan() -> None:
    """Scheduled profile carries thr0 + c.|qdot_plan| + a.|qddot_plan| with the accel term on."""
    config = _config(
        ThresholdMode.TRAJECTORY_SCHEDULED,
        vel_coeff=(0.05,) * 7,
        acc_coeff=(0.2,) * 7,
        use_accel_term=True,
    )
    planned_qdot = ((1.0,) * 7, (2.0,) * 7)
    planned_qddot = ((4.0,) * 7, (-5.0,) * 7)
    schedule = build_schedule(config, planned_qdot, planned_qddot)
    for joint in range(7):
        assert schedule.at(0)[joint] == pytest.approx(_THR0[joint] + 0.05 * 1.0 + 0.2 * 4.0)
        assert schedule.at(1)[joint] == pytest.approx(_THR0[joint] + 0.05 * 2.0 + 0.2 * 5.0)


def test_build_schedule_drops_accel_term_when_off() -> None:
    """With the accel term off, the scheduled profile carries only the velocity term."""
    config = _config(
        ThresholdMode.TRAJECTORY_SCHEDULED,
        vel_coeff=(0.05,) * 7,
        acc_coeff=(0.2,) * 7,
        use_accel_term=False,
    )
    schedule = build_schedule(config, ((2.0,) * 7,), ((9.0,) * 7,))
    for joint in range(7):
        assert schedule.at(0)[joint] == pytest.approx(_THR0[joint] + 0.05 * 2.0)


def test_schedule_clamps_past_end() -> None:
    """A step past the planned horizon holds the last profile, not a bare STATIC vector."""
    schedule = ThresholdSchedule(samples=((1.0,) * 7, (2.0,) * 7))
    assert schedule.at(5) == (2.0,) * 7


def test_empty_schedule_is_refused() -> None:
    """Reading an empty schedule is refused rather than returning a default."""
    with pytest.raises(ThresholdConfigError, match="empty"):
        ThresholdSchedule(samples=()).at(0)


def test_build_schedule_refuses_mismatched_lengths() -> None:
    """Planned velocity and acceleration of different lengths are refused."""
    config = _config(ThresholdMode.TRAJECTORY_SCHEDULED)
    with pytest.raises(ThresholdConfigError, match="steps"):
        build_schedule(config, ((0.0,) * 7, (0.0,) * 7), ((0.0,) * 7,))
