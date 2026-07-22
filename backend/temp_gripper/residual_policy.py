"""Why the gripper is excluded from residual (GMO) collision detection, and the guard.

FR-SAF-024: the gripper (J8) carries no residual-based collision detection by default,
and the reason is NOT that its torque is unobserved — it IS observed (the LeRobot
follower fills gripper.torque, spec 12 FR-SAF-024). The reason is the pair of facts
WP-2B-01 already records as `GRIPPER_MODEL_REASON`: there is no finger dynamics model
(no finger links in the inertials, empty friction table) and a grasp reaction is a
constant torque offset, so a residual cannot separate "collision" from "grasp". This
module reuses that single reason rather than restating it, and enforces the exclusion
on a per-joint residual vector.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.dynamics.constants import GRIPPER_MODEL_REASON
from backend.temp_gripper.constants import (
    GRIPPER_JOINT_INDEX,
    GRIPPER_TORQUE_IS_OBSERVED,
    MOTOR_COUNT_PER_ARM,
)
from backend.temp_gripper.errors import TempGripperConfigError

# The residual-exclusion reason, framed for detection over the single WP-2B-01 fact
# pair. Composed by reference so the two facts (no finger dynamics model; grasp
# reaction = constant torque offset) keep one owner and cannot drift. The trailing
# clause asserts positively that torque IS observed — the reason is stated as the two
# facts, never as "no torque observation" (the wrong v1 rationale, FR-MAN-057's
# ros2_control path, which is not our LeRobot path), and it carries no such phrase even
# negated, so any substring audit sees only the model-and-offset rationale.
GRIPPER_RESIDUAL_DISABLED_REASON = (
    "gripper residual (GMO) collision detection is disabled by default: "
    + GRIPPER_MODEL_REASON
    + "; the gripper's torque is in fact observed, so the disable is the missing "
    "dynamics model and the grasp-reaction offset"
)


def gripper_torque_is_observed() -> bool:
    """Whether the gripper's torque is observed (it is — see the module docstring)."""
    return GRIPPER_TORQUE_IS_OBSERVED


def residual_detection_enabled_for(motor_index: int) -> bool:
    """Whether residual collision detection applies to a motor.

    False for a gripper motor (the last motor of each per-arm block), True for an arm
    joint. The gripper exclusion is the FR-SAF-024 default; the reason is
    `GRIPPER_RESIDUAL_DISABLED_REASON`. The per-arm modulo lets one function serve a
    single-arm and a concatenated bimanual motor vector alike.

    Args:
        motor_index: 0-based index into a per-arm or concatenated multi-arm motor vector.

    Returns:
        (bool) True iff the motor is an arm joint.

    Raises:
        TempGripperConfigError: If `motor_index` is negative.
    """
    if motor_index < 0:
        raise TempGripperConfigError(f"motor index must be non-negative, got {motor_index}")
    return (motor_index % MOTOR_COUNT_PER_ARM) != GRIPPER_JOINT_INDEX


def gripper_motor_indices(motor_count: int) -> tuple[int, ...]:
    """The gripper positions in a full per-arm-block motor vector.

    Args:
        motor_count: Vector length; must be a positive multiple of `MOTOR_COUNT_PER_ARM`
            (the layout the gripper index is defined against).

    Returns:
        (tuple) The 0-based gripper indices, one per arm block.

    Raises:
        TempGripperConfigError: If `motor_count` is not a positive multiple of the
            per-arm motor count.
    """
    if motor_count <= 0 or motor_count % MOTOR_COUNT_PER_ARM != 0:
        raise TempGripperConfigError(
            f"residual vector length must be a positive multiple of {MOTOR_COUNT_PER_ARM}, "
            f"got {motor_count}"
        )
    blocks = motor_count // MOTOR_COUNT_PER_ARM
    return tuple(block * MOTOR_COUNT_PER_ARM + GRIPPER_JOINT_INDEX for block in range(blocks))


def mask_gripper_residual(residual: Sequence[float]) -> tuple[float, ...]:
    """Zero the gripper entries of a residual vector so no threshold can trip on them.

    A per-joint collision check thresholds each entry of the residual; setting the
    gripper entries to zero is how "residual detection is not applied to the gripper" is
    enforced on that check — a zero can never exceed a positive threshold. Arm-joint
    entries are returned unchanged. An arm-only residual vector (which already excludes
    the gripper) needs no masking and is not the input here.

    Args:
        residual: A full per-arm-block residual vector (length a multiple of
            `MOTOR_COUNT_PER_ARM`).

    Returns:
        (tuple) The residual with every gripper entry set to 0.0.

    Raises:
        TempGripperConfigError: If the vector length is not a positive multiple of the
            per-arm motor count.
    """
    grippers = set(gripper_motor_indices(len(residual)))
    return tuple(0.0 if index in grippers else float(value) for index, value in enumerate(residual))
