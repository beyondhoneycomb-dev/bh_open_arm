"""The dry-run limit tables: torque (frozen) and velocity (candidate canons).

Torque (`09` FR-SIM-030 ③, acceptance ⑦) is the one confirmed table: J1/J2
±40, J3/J4 ±27, J5-J7 ±7 Nm, matching the MJCF ``actuatorfrcrange`` and the
DM motor force ranges. Each limit is an ``Nm`` (CTR-UNIT@v1) so a torque check
cannot silently receive a packet-scale value; the type is the guard.

The gripper is deliberately absent from the torque table: `09` §5 Q2 leaves the
gripper torque canon undecided (the POS_FORCE second value is a dimensionless
``torque_pu``, not Nm), and the spec states check ③ "cannot be applied to the
gripper" until a real force calibration lands. Including a fabricated gripper Nm
limit would be inventing the very number Q2 says does not yet exist, so the
torque check covers the fourteen arm joints only, and that exclusion is recorded
rather than papered over.

Velocity (`09` FR-SIM-032, §5 Q4) is decision-required: three real candidate
tables exist and no canon is chosen. This module transcribes the two per-joint
candidates as selectable tables; it does not pick one. Choosing is mandatory at
run time (`canon.py`), and a dry-run with no velocity canon selected is refused,
never run with a default — a default would be the invented answer Q4 forbids.
"""

from __future__ import annotations

from contracts.units.tags import Nm

# Arm motor keys in LeRobot arm-major order (left then right), joint_1..joint_7.
# The gripper is excluded: it carries no confirmed torque canon (Q2).
ARM_SIDES = ("left", "right")
ARM_JOINT_NUMBERS = (1, 2, 3, 4, 5, 6, 7)


def arm_motor_keys() -> tuple[str, ...]:
    """Return the fourteen arm motor keys the per-joint checks cover.

    Returns:
        (tuple[str, ...]) ``left_joint_1`` .. ``right_joint_7`` in arm-major order.
    """
    return tuple(f"{side}_joint_{number}" for side in ARM_SIDES for number in ARM_JOINT_NUMBERS)


# `09` FR-SIM-030 ③ torque limits in newton-metres, by joint number. Symmetric:
# the bound is +/- this magnitude. J1/J2 = DM8009, J3/J4 = DM4340, J5-J7 = DM4310.
_TORQUE_LIMIT_NM_BY_JOINT = {
    1: 40.0,
    2: 40.0,
    3: 27.0,
    4: 27.0,
    5: 7.0,
    6: 7.0,
    7: 7.0,
}


def torque_limits_nm() -> dict[str, Nm]:
    """Return the per-arm-joint torque limit as an ``Nm`` (acceptance ⑦).

    Returns:
        (dict[str, Nm]) Motor key to its symmetric torque bound magnitude in Nm.
    """
    return {
        f"{side}_joint_{number}": Nm(_TORQUE_LIMIT_NM_BY_JOINT[number])
        for side in ARM_SIDES
        for number in ARM_JOINT_NUMBERS
    }


# `09` FR-SIM-032 velocity candidate tables (rad/s), by joint number. Both are
# fully per-joint and real; which one is canon is decision-required (Q4), so this
# module offers them and refuses to choose.
_URDF_VELOCITY_RAD_S_BY_JOINT = {
    1: 16.755,
    2: 16.755,
    3: 5.4454,
    4: 5.4454,
    5: 20.944,
    6: 20.944,
    7: 20.944,
}
_OPENARM_CONTROL_VELOCITY_RAD_S_BY_JOINT = {
    1: 1.57,
    2: 1.57,
    3: 3.14,
    4: 3.14,
    5: 12.6,
    6: 12.6,
    7: 12.6,
}


def urdf_velocity_limits_rad_s() -> dict[str, float]:
    """Return the URDF velocity candidate table (rad/s), keyed by motor key."""
    return _velocity_table(_URDF_VELOCITY_RAD_S_BY_JOINT)


def openarm_control_velocity_limits_rad_s() -> dict[str, float]:
    """Return the ``openarm_control`` velocity candidate table (rad/s)."""
    return _velocity_table(_OPENARM_CONTROL_VELOCITY_RAD_S_BY_JOINT)


def _velocity_table(by_joint: dict[int, float]) -> dict[str, float]:
    """Expand a per-joint-number velocity table into per-motor-key form."""
    return {
        f"{side}_joint_{number}": by_joint[number]
        for side in ARM_SIDES
        for number in ARM_JOINT_NUMBERS
    }
