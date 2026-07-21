"""Resolve motor keys to MuJoCo model addresses by name (not by index).

`09` (WP-0C-04) requires indices to be resolved at run time from joint names, not
hard-coded positional slices, so a change in MJCF qpos ordering cannot silently
mis-address a joint. The per-joint dry-run checks (position, velocity, torque,
lifter) all need the same mapping — motor key to ``(qpos_adr, dof_adr, jnt_id)`` —
so it lives here once rather than being re-derived in each check file.

A dry-run motor key (``left_joint_1``) maps to the MJCF joint name
``openarm_left_joint1``; the lifter is the single prismatic
``openarm_lifter_joint``. This module reads addresses through ``mujoco.mj_name2id``
and the model's ``jnt_qposadr``/``jnt_dofadr`` tables, so it is robust to qpos
reordering exactly as the upstream kinematics claims to be.
"""

from __future__ import annotations

from dataclasses import dataclass

import mujoco

from sim.dryrun.limits import ARM_JOINT_NUMBERS, ARM_SIDES

# The single prismatic lifter joint whose stroke check ⑥ bounds to [0, 0.3] m.
LIFTER_JOINT_NAME = "openarm_lifter_joint"


@dataclass(frozen=True)
class JointAddress:
    """One joint's addresses in a compiled model.

    Attributes:
        motor_key: The dry-run motor key (``left_joint_1``) or lifter name.
        mjcf_name: The MJCF joint name (``openarm_left_joint1``).
        jnt_id: The joint id in the compiled model.
        qpos_adr: The joint's address in ``data.qpos``.
        dof_adr: The joint's address in ``data.qvel`` / dof-indexed arrays.
    """

    motor_key: str
    mjcf_name: str
    jnt_id: int
    qpos_adr: int
    dof_adr: int


def _mjcf_arm_name(side: str, number: int) -> str:
    """Return the MJCF joint name for an arm side and joint number."""
    return f"openarm_{side}_joint{number}"


def resolve_joint(model: mujoco.MjModel, motor_key: str, mjcf_name: str) -> JointAddress:
    """Resolve one joint's addresses by name, raising if the asset lacks it.

    Args:
        model: The compiled model.
        motor_key: The dry-run motor key this address is reported under.
        mjcf_name: The MJCF joint name to look up.

    Returns:
        (JointAddress) The resolved addresses.

    Raises:
        ValueError: If the joint is absent from the model.
    """
    jnt_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, mjcf_name)
    if jnt_id < 0:
        raise ValueError(f"joint {mjcf_name!r} (for {motor_key!r}) is absent from the model")
    return JointAddress(
        motor_key=motor_key,
        mjcf_name=mjcf_name,
        jnt_id=jnt_id,
        qpos_adr=int(model.jnt_qposadr[jnt_id]),
        dof_adr=int(model.jnt_dofadr[jnt_id]),
    )


def arm_joint_addresses(model: mujoco.MjModel) -> tuple[JointAddress, ...]:
    """Resolve every arm joint's address, in arm-major joint order.

    Args:
        model: The compiled model.

    Returns:
        (tuple[JointAddress, ...]) The fourteen arm joint addresses.
    """
    return tuple(
        resolve_joint(model, f"{side}_joint_{number}", _mjcf_arm_name(side, number))
        for side in ARM_SIDES
        for number in ARM_JOINT_NUMBERS
    )


def lifter_address(model: mujoco.MjModel) -> JointAddress:
    """Resolve the prismatic lifter joint's address.

    Args:
        model: The compiled model.

    Returns:
        (JointAddress) The lifter joint address.
    """
    return resolve_joint(model, LIFTER_JOINT_NAME, LIFTER_JOINT_NAME)
