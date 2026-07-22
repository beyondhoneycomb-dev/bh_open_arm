"""The frozen defaults and the config/calibration validation bands (spec 12 §2.12 [A]).

The defaults are part of the contract, so they are asserted as exact values. Every range and band
refusal is asserted too: a mis-specified threshold must be rejected at construction, never clamped,
so it can never reach the residual comparison.
"""

from __future__ import annotations

import pytest

from backend.threshold import (
    ThresholdCalibration,
    ThresholdConfig,
    ThresholdConfigError,
    ThresholdMode,
)
from backend.threshold.constants import (
    ACC_COEFF_DEFAULT,
    CONFIRM_SAMPLES_DEFAULT,
    HYSTERESIS_RATIO_DEFAULT,
    JOINT_EFFORT_LIMITS_NM,
    THRESHOLD_DEFAULT_NM,
    THRESHOLD_MIN_NM,
    VEL_COEFF_DEFAULT,
)


def test_default_config_matches_spec_table() -> None:
    """`ThresholdConfig.default()` is the spec 12 §2.12 [A] default row."""
    config = ThresholdConfig.default()
    assert config.mode is ThresholdMode.VELOCITY_SCALED
    assert config.vel_coeff == (VEL_COEFF_DEFAULT,) * 7 == (0.05,) * 7
    assert config.acc_coeff == (ACC_COEFF_DEFAULT,) * 7 == (0.0,) * 7
    assert config.use_accel_term is False
    assert config.confirm_samples == CONFIRM_SAMPLES_DEFAULT == 5
    assert config.hysteresis_ratio == HYSTERESIS_RATIO_DEFAULT == 0.7
    assert config.per_joint_enable == (True,) * 7


def test_literature_default_is_ten_percent_of_effort() -> None:
    """The FR-SAF-020 base threshold is exactly 0.1 x the URDF effort limit."""
    calibration = ThresholdCalibration.literature_default()
    assert calibration.thr0 == THRESHOLD_DEFAULT_NM == (4.0, 4.0, 2.7, 2.7, 0.7, 0.7, 0.7)
    assert calibration.thr0 == tuple(round(0.1 * effort, 6) for effort in JOINT_EFFORT_LIMITS_NM)


def test_calibration_refuses_threshold_below_lsb_floor() -> None:
    """A base threshold below 10 x LSB is refused — it would fire on the quantiser (FR-SAF-019)."""
    below_floor = list(THRESHOLD_DEFAULT_NM)
    below_floor[6] = THRESHOLD_MIN_NM[6] / 2.0
    with pytest.raises(ThresholdConfigError, match="joint7"):
        ThresholdCalibration.from_calibration(tuple(below_floor))


def test_calibration_refuses_threshold_above_effort_ceiling() -> None:
    """A base threshold above the joint effort limit is refused — detection would be dead."""
    above_ceiling = list(THRESHOLD_DEFAULT_NM)
    above_ceiling[0] = JOINT_EFFORT_LIMITS_NM[0] + 1.0
    with pytest.raises(ThresholdConfigError, match="joint1"):
        ThresholdCalibration.from_calibration(tuple(above_ceiling))


def test_calibration_accepts_measured_value_inside_band() -> None:
    """A measured per-joint threshold inside [10 x LSB, effort] is accepted."""
    measured = (5.0, 3.8, 3.0, 2.0, 0.5, 0.4, 0.3)
    calibration = ThresholdCalibration.from_calibration(measured)
    assert calibration.thr0 == measured


def test_calibration_refuses_wrong_width() -> None:
    """A base-threshold vector that is not 7 joints wide is refused."""
    with pytest.raises(ThresholdConfigError, match="7 joints wide"):
        ThresholdCalibration(thr0=(4.0, 4.0, 2.7))


@pytest.mark.parametrize("confirm_samples", [0, 51])
def test_config_refuses_confirm_samples_out_of_range(confirm_samples: int) -> None:
    """confirm_samples outside [1, 50] is refused."""
    with pytest.raises(ThresholdConfigError, match="confirm_samples"):
        _config_with(confirm_samples=confirm_samples)


@pytest.mark.parametrize("hysteresis_ratio", [0.2, 0.99])
def test_config_refuses_hysteresis_out_of_range(hysteresis_ratio: float) -> None:
    """hysteresis_ratio outside [0.3, 0.95] is refused."""
    with pytest.raises(ThresholdConfigError, match="hysteresis_ratio"):
        _config_with(hysteresis_ratio=hysteresis_ratio)


def test_config_refuses_vel_coeff_out_of_range() -> None:
    """A velocity coefficient outside [0, 1.0] is refused."""
    with pytest.raises(ThresholdConfigError, match="vel_coeff"):
        _config_with(vel_coeff=(0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 1.5))


def test_config_refuses_acc_coeff_out_of_range() -> None:
    """An acceleration coefficient outside [0, 0.5] is refused."""
    with pytest.raises(ThresholdConfigError, match="acc_coeff"):
        _config_with(acc_coeff=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.9))


def test_config_refuses_wrong_width_enable() -> None:
    """A per_joint_enable vector that is not 7 wide is refused."""
    with pytest.raises(ThresholdConfigError, match="per_joint_enable"):
        _config_with(per_joint_enable=(True,) * 6)


def _config_with(
    *,
    confirm_samples: int = CONFIRM_SAMPLES_DEFAULT,
    hysteresis_ratio: float = HYSTERESIS_RATIO_DEFAULT,
    vel_coeff: tuple[float, ...] = (VEL_COEFF_DEFAULT,) * 7,
    acc_coeff: tuple[float, ...] = (ACC_COEFF_DEFAULT,) * 7,
    per_joint_enable: tuple[bool, ...] = (True,) * 7,
) -> ThresholdConfig:
    """Build a config overriding one field, so each refusal test isolates one invariant."""
    return ThresholdConfig(
        calibration=ThresholdCalibration.literature_default(),
        mode=ThresholdMode.VELOCITY_SCALED,
        vel_coeff=vel_coeff,
        acc_coeff=acc_coeff,
        use_accel_term=False,
        confirm_samples=confirm_samples,
        hysteresis_ratio=hysteresis_ratio,
        per_joint_enable=per_joint_enable,
    )
