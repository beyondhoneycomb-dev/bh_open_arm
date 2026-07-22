"""CTR-CAL@v1 shape invariants and the residual arithmetic.

These pin the frozen schema's guarantees the field types cannot: per-motor vector
widths, the sign domain, the side domain, checksum integrity, and unknown-field
rejection — plus the pure residual computation the set-zero flow and the power-cycle
re-verify both call.
"""

from __future__ import annotations

import pytest

from backend.calibration.schema import (
    MOTOR_COUNT,
    MOTOR_ORDER,
    ZERO_RESIDUAL_TOLERANCE_DEG,
    CalibrationError,
    OpenArmCalibration,
    ZeroMethod,
)
from backend.calibration.verify import compute_residual


def _valid() -> OpenArmCalibration:
    return OpenArmCalibration(
        robot_type="oa_openarm_follower",
        robot_id="s",
        side="left",
        motor_zero_raw=[0.0] * MOTOR_COUNT,
        urdf_zero_offset=[0.0] * MOTOR_COUNT,
        gripper_open_rad=0.0,
        gripper_close_rad=-0.7,
    )


def test_vectors_must_be_eight_long() -> None:
    """A per-motor vector of the wrong length is rejected."""
    with pytest.raises(CalibrationError):
        OpenArmCalibration(
            robot_type="oa",
            robot_id="s",
            side="left",
            motor_zero_raw=[0.0] * (MOTOR_COUNT - 1),
            urdf_zero_offset=[0.0] * MOTOR_COUNT,
            gripper_open_rad=0.0,
            gripper_close_rad=0.0,
        )


def test_signs_must_be_plus_or_minus_one() -> None:
    """A joint sign outside {-1, +1} is rejected."""
    with pytest.raises(CalibrationError):
        OpenArmCalibration(**{**_valid().__dict__, "joint_signs": [2] * MOTOR_COUNT})


def test_side_domain_is_enforced() -> None:
    """A side other than left/right is rejected."""
    with pytest.raises(CalibrationError):
        OpenArmCalibration(**{**_valid().__dict__, "side": "middle"})


def test_unknown_field_is_rejected_on_load() -> None:
    """A JSON object carrying an unknown field is rejected (frozen shape is closed)."""
    payload = _valid().to_json_dict()
    payload["surprise"] = 1
    with pytest.raises(CalibrationError):
        OpenArmCalibration.from_json_dict(payload)


def test_checksum_is_content_addressed() -> None:
    """The checksum is a function of the body and detects a mutated field."""
    calibration = _valid()
    good = calibration.to_json_dict()
    assert OpenArmCalibration.from_json_dict(good).checksum == good["checksum"]
    good["gripper_open_rad"] = 3.0  # mutate without re-hashing
    with pytest.raises(CalibrationError):
        OpenArmCalibration.from_json_dict(good)


def test_residual_flags_offenders_by_name() -> None:
    """The residual computation names exactly the joints past tolerance."""
    measured = [0.0] * MOTOR_COUNT
    reference = [0.0] * MOTOR_COUNT
    reference[0] = 1.0  # joint_1 off by 1.0°
    reference[7] = 0.1  # gripper within ±0.5°
    result = compute_residual(measured, reference)
    assert result.within_tolerance is False
    assert result.offenders == (MOTOR_ORDER[0],)
    assert result.tolerance_deg == ZERO_RESIDUAL_TOLERANCE_DEG


def test_residual_within_tolerance_is_clean() -> None:
    """A readback matching the reference within tolerance passes with no offenders."""
    result = compute_residual([0.3] * MOTOR_COUNT, [0.0] * MOTOR_COUNT)
    assert result.within_tolerance is True
    assert result.offenders == ()


def test_zero_method_enum_roundtrips_through_json() -> None:
    """`zero_method` survives serialization as its string value."""
    calibration = OpenArmCalibration(
        **{**_valid().__dict__, "zero_method": ZeroMethod.MECHANICAL_JIG}
    )
    assert calibration.to_json_dict()["zero_method"] == "mechanical_jig"
    assert OpenArmCalibration.from_json_dict(calibration.to_json_dict()).zero_method is (
        ZeroMethod.MECHANICAL_JIG
    )
