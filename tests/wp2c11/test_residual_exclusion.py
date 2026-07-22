"""Acceptance ① — residual (GMO) collision detection is not applied to gripper joints.

The exclusion is enforced two ways: the per-motor gate returns False for a gripper
motor, and masking a full-motor residual zeroes the gripper entries so a per-joint
threshold check can never trip on them. A synthetic gripper-residual spike demonstrates
the mask: a magnitude that would trip any positive threshold becomes zero.
"""

from __future__ import annotations

import pytest

from backend.temp_gripper.constants import GRIPPER_JOINT_INDEX, MOTOR_COUNT_PER_ARM
from backend.temp_gripper.errors import TempGripperConfigError
from backend.temp_gripper.residual_policy import (
    gripper_motor_indices,
    mask_gripper_residual,
    residual_detection_enabled_for,
)

_COLLISION_THRESHOLD = 5.0
_GRIPPER_SPIKE = 999.0


def test_arm_joints_are_enabled_gripper_is_not() -> None:
    for arm_joint in range(GRIPPER_JOINT_INDEX):
        assert residual_detection_enabled_for(arm_joint)
    assert not residual_detection_enabled_for(GRIPPER_JOINT_INDEX)


def test_bimanual_second_gripper_is_also_excluded() -> None:
    # The second arm's gripper sits at MOTOR_COUNT_PER_ARM + GRIPPER_JOINT_INDEX.
    second_gripper = MOTOR_COUNT_PER_ARM + GRIPPER_JOINT_INDEX
    assert not residual_detection_enabled_for(second_gripper)
    assert residual_detection_enabled_for(MOTOR_COUNT_PER_ARM)  # first arm joint of arm 2


def test_negative_index_is_refused() -> None:
    with pytest.raises(TempGripperConfigError, match="non-negative"):
        residual_detection_enabled_for(-1)


def test_gripper_indices_single_and_bimanual() -> None:
    assert gripper_motor_indices(MOTOR_COUNT_PER_ARM) == (GRIPPER_JOINT_INDEX,)
    assert gripper_motor_indices(2 * MOTOR_COUNT_PER_ARM) == (
        GRIPPER_JOINT_INDEX,
        MOTOR_COUNT_PER_ARM + GRIPPER_JOINT_INDEX,
    )


def test_masking_zeroes_a_gripper_residual_spike() -> None:
    residual = [0.0] * MOTOR_COUNT_PER_ARM
    residual[GRIPPER_JOINT_INDEX] = _GRIPPER_SPIKE
    masked = mask_gripper_residual(residual)
    # Unmasked, the spike would trip the collision threshold; masked, it cannot.
    assert residual[GRIPPER_JOINT_INDEX] > _COLLISION_THRESHOLD
    assert masked[GRIPPER_JOINT_INDEX] == 0.0
    assert max(masked) <= _COLLISION_THRESHOLD


def test_masking_keeps_arm_residuals() -> None:
    residual = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, _GRIPPER_SPIKE]
    masked = mask_gripper_residual(residual)
    assert masked[:GRIPPER_JOINT_INDEX] == (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0)
    assert masked[GRIPPER_JOINT_INDEX] == 0.0


def test_masking_bimanual_zeroes_both_grippers() -> None:
    residual = [1.0] * (2 * MOTOR_COUNT_PER_ARM)
    masked = mask_gripper_residual(residual)
    for gripper in gripper_motor_indices(len(residual)):
        assert masked[gripper] == 0.0
    assert masked[0] == 1.0


def test_masking_refuses_a_non_block_length() -> None:
    with pytest.raises(TempGripperConfigError, match="positive multiple"):
        mask_gripper_residual([0.0] * (MOTOR_COUNT_PER_ARM - 1))
