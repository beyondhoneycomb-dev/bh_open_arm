"""Acceptance ④ ⑤: the ten-LSB threshold floor blocks, and the default carries its label.

The floor figures are re-derived here from the packet T_MAX table and asserted against the
spec-quoted values (DM8009 0.264 / DM4340 0.137 / DM4310 0.049 Nm), so a drift in either the
table or the quoted floor is caught rather than passing on a re-typed literal.
"""

from __future__ import annotations

import pytest

from backend.can.rid.motor_limits import MotorType
from backend.safety_bringup import (
    ThresholdBelowFloorError,
    assert_threshold_above_floor,
    default_collision_thresholds,
    floor_for_joint,
    floor_for_motor,
)
from backend.safety_bringup.constants import THEORETICAL_THRESHOLD_LABEL


def test_floor_matches_spec_quoted_values() -> None:
    # ④: LSB*10 floor per motor equals the spec's DM8009 0.264 / DM4340 0.137 / DM4310 0.049.
    assert floor_for_motor(MotorType.DM8009) == pytest.approx(0.264, abs=1e-3)
    assert floor_for_motor(MotorType.DM4340) == pytest.approx(0.137, abs=1e-3)
    assert floor_for_motor(MotorType.DM4310) == pytest.approx(0.049, abs=1e-3)


def test_threshold_below_floor_is_blocked_for_each_motor() -> None:
    # ④: a threshold just under the floor is refused, per motor type.
    for joint_index, motor in ((0, MotorType.DM8009), (2, MotorType.DM4340), (4, MotorType.DM4310)):
        floor = floor_for_joint(joint_index)
        with pytest.raises(ThresholdBelowFloorError, match=motor.value):
            assert_threshold_above_floor(joint_index, floor - 1e-4)


def test_threshold_at_or_above_floor_is_allowed() -> None:
    for joint_index in range(7):
        floor = floor_for_joint(joint_index)
        assert_threshold_above_floor(joint_index, floor)
        assert_threshold_above_floor(joint_index, floor + 1.0)


def test_default_thresholds_are_ten_percent_of_effort() -> None:
    # ⑤: defaults are +-10% of URDF effort: [4,4,2.7,2.7,0.7,0.7,0.7].
    defaults = default_collision_thresholds()
    assert defaults.thresholds_nm == pytest.approx((4.0, 4.0, 2.7, 2.7, 0.7, 0.7, 0.7))


def test_default_thresholds_carry_theoretical_label() -> None:
    # ⑤: the "theoretical starting point, not OpenArm-measured" label is present.
    defaults = default_collision_thresholds()
    assert defaults.label == THEORETICAL_THRESHOLD_LABEL
    assert "NOT an OpenArm-measured value" in defaults.label


def test_default_thresholds_stay_above_floor() -> None:
    # A sanity coupling: every labelled default sits above its own physics floor.
    defaults = default_collision_thresholds()
    for joint_index, threshold in enumerate(defaults.thresholds_nm):
        assert threshold > floor_for_joint(joint_index)
