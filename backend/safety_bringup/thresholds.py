"""Per-joint collision torque thresholds: a physics-owned floor and a labelled default.

Two `12` requirements meet here. FR-SAF-019 makes the floor physics-owned: a per-joint
collision threshold may not be set below ten torque-field LSBs, because below that it is
indistinguishable from quantisation noise. The floor is derived from the packet T_MAX
table (`constants.torque_lsb_nm`), so a user cannot lower it — `set_threshold` refuses a
value under it rather than clamping silently.

FR-SAF-020 makes the default honest: the starting threshold is +-10% of the URDF effort
limit ([4.0, 4.0, 2.7, 2.7, 0.7, 0.7, 0.7] Nm), a literature-rule figure and *not* an
OpenArm-measured value. The default carries that label as a first-class field so the
static check (acceptance ⑤) can see it; a default without the label would let a
theoretical number pass for a measured one.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.can.rid.motor_limits import MotorType
from backend.safety_bringup.constants import (
    ARM_JOINT_MOTORS,
    DEFAULT_COLLISION_THRESHOLD_FRACTION,
    THEORETICAL_THRESHOLD_LABEL,
    URDF_EFFORT_LIMIT_NM,
    collision_threshold_floor_nm,
)


class ThresholdBelowFloorError(Exception):
    """Raised when a collision threshold is set below its ten-LSB physics floor.

    The floor is owned by physics, not the user (`12` FR-SAF-019). Refusing rather than
    clamping keeps the caller from believing a sub-noise threshold was accepted.
    """


@dataclass(frozen=True)
class DefaultCollisionThresholds:
    """The default per-joint collision thresholds and their mandatory provenance label.

    Attributes:
        thresholds_nm: Per-joint default threshold, +-10% of the URDF effort limit.
        label: The `12` FR-SAF-020 provenance label marking these as a theoretical
            starting point, not an OpenArm-measured value. Its presence is the fact
            acceptance ⑤ checks statically.
    """

    thresholds_nm: tuple[float, ...]
    label: str


def default_collision_thresholds() -> DefaultCollisionThresholds:
    """Build the labelled default collision thresholds (`12` FR-SAF-020, acceptance ⑤).

    Returns:
        (DefaultCollisionThresholds) The +-10%-of-effort defaults with the theoretical
        label attached.
    """
    thresholds = tuple(
        effort * DEFAULT_COLLISION_THRESHOLD_FRACTION for effort in URDF_EFFORT_LIMIT_NM
    )
    return DefaultCollisionThresholds(thresholds_nm=thresholds, label=THEORETICAL_THRESHOLD_LABEL)


def floor_for_joint(joint_index: int) -> float:
    """Return the ten-LSB collision-threshold floor for an arm joint (`12` FR-SAF-019).

    Args:
        joint_index: Zero-based arm joint index (0 == J1).

    Returns:
        (float) The lowest admissible threshold at this joint, Nm.
    """
    return collision_threshold_floor_nm(ARM_JOINT_MOTORS[joint_index])


def floor_for_motor(motor: MotorType) -> float:
    """Return the ten-LSB collision-threshold floor for a motor type (`12` FR-SAF-019).

    Args:
        motor: The motor family.

    Returns:
        (float) The lowest admissible threshold for that motor, Nm.
    """
    return collision_threshold_floor_nm(motor)


def assert_threshold_above_floor(joint_index: int, threshold_nm: float) -> None:
    """Refuse a collision threshold set below its physics floor (`12` FR-SAF-019, ④).

    Args:
        joint_index: Zero-based arm joint index.
        threshold_nm: The proposed collision torque threshold, Nm.

    Raises:
        ThresholdBelowFloorError: If the threshold is below ten torque-field LSBs for the
            motor at this joint.
    """
    floor = floor_for_joint(joint_index)
    if threshold_nm < floor:
        motor = ARM_JOINT_MOTORS[joint_index]
        raise ThresholdBelowFloorError(
            f"joint {joint_index} ({motor.value}): threshold {threshold_nm} Nm is below the "
            f"ten-LSB floor {floor:.4f} Nm; the floor is physics-owned and cannot be lowered "
            "(12 FR-SAF-019)"
        )
