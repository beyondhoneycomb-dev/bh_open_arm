"""The pure left/right mirror transform (WP-2D-08 core).

Joint space and pose reflection only — no IK, no FK, no robot stack, so the convention
is exercisable without mujoco or LeRobot. Every function here is its own inverse:
mirroring a mirrored value returns the original *exactly* (each element is one IEEE-754
sign flip), which is the FR-MAN-046 "numeric verification error 0.0" property that
``verify.involution_error`` measures. Agreement with the real kinematics and with the
pinned joint limits is proven in ``verify`` and the acceptance suite, which reuse
``sim.ik`` and the WP-2D-01 kinematics rather than re-deriving them here.
"""

from __future__ import annotations

import numpy as np

from backend.mirror.constants import (
    ARM_JOINT_COUNT,
    ARM_MIRROR_SIGNS,
    GRIPPER_INDEX,
    OPPOSITE_SIDE,
    POSE_WIDTH,
    POSITION_REFLECT,
    Q_URDF_WIDTH,
    QUAT_REFLECT,
)


def mirror_arm_side(side: str) -> str:
    """Return the opposite arm side.

    Args:
        side: ``"right"`` or ``"left"``.

    Returns:
        (str) The opposite side.

    Raises:
        ValueError: If ``side`` is not ``"right"`` or ``"left"``.
    """
    if side not in OPPOSITE_SIDE:
        raise ValueError(f"side must be 'right' or 'left', got {side!r}")
    return OPPOSITE_SIDE[side]


def mirror_arm_joints(q_arm: np.ndarray) -> np.ndarray:
    """Return the seven arm joints mirrored by the FR-MAN-046 sign vector.

    joint4 (index 3) keeps its sign; the other six flip. The sign vector is its own
    inverse, so ``mirror_arm_joints(mirror_arm_joints(q)) == q`` exactly.

    Args:
        q_arm: The seven arm joint angles (radians), any array-like.

    Returns:
        (np.ndarray) The mirrored seven-vector.

    Raises:
        ValueError: If the input is not length seven.
    """
    joints = np.asarray(q_arm, dtype=float)
    if joints.shape != (ARM_JOINT_COUNT,):
        raise ValueError(f"arm joints must be {ARM_JOINT_COUNT}-vector, got shape {joints.shape}")
    return joints * ARM_MIRROR_SIGNS


def mirror_gripper(value: float) -> float:
    """Return the gripper angle sign-flipped (right opens negative, left positive).

    FR-MAN-046: the gripper opening reflects, so ``g_left = -g_right``. Independent of
    LeRobot's left-gripper soft limit, which ships the mirror bug (FR-MAN-017).

    Args:
        value: The gripper finger-joint angle (radians).

    Returns:
        (float) The sign-flipped angle.
    """
    return -float(value)


def mirror_q_urdf(q_urdf: np.ndarray) -> np.ndarray:
    """Return the full eight-value driver vector mirrored (seven joints + gripper).

    Args:
        q_urdf: The eight-value ``[j1..j7, gripper]`` vector (radians), any array-like.

    Returns:
        (np.ndarray) The mirrored eight-vector; an exact involution of the input.

    Raises:
        ValueError: If the input is not length eight.
    """
    q = np.asarray(q_urdf, dtype=float)
    if q.shape != (Q_URDF_WIDTH,):
        raise ValueError(f"q_urdf must be {Q_URDF_WIDTH}-vector, got shape {q.shape}")
    out = q.copy()
    out[:ARM_JOINT_COUNT] = mirror_arm_joints(q[:ARM_JOINT_COUNT])
    out[GRIPPER_INDEX] = mirror_gripper(q[GRIPPER_INDEX])
    return out


def reflect_ee_pose(pose: np.ndarray) -> np.ndarray:
    """Return an EE pose reflected across the cell's sagittal (XZ) plane.

    Position reflects the y axis; orientation reflects by the (qw, -qx, qy, -qz) sign
    pattern. Both are exact sign flips, so the reflection is its own inverse, and both
    equal the FK of the joint-space mirror to floating point (test_fk_equality).

    Args:
        pose: The seven-value ``[px, py, pz, qw, qx, qy, qz]`` world pose, array-like.

    Returns:
        (np.ndarray) The reflected seven-value pose.

    Raises:
        ValueError: If the input is not length seven.
    """
    p = np.asarray(pose, dtype=float)
    if p.shape != (POSE_WIDTH,):
        raise ValueError(f"ee_pose must be {POSE_WIDTH}-vector, got shape {p.shape}")
    out = p.copy()
    out[:3] = p[:3] * POSITION_REFLECT
    out[3:POSE_WIDTH] = p[3:POSE_WIDTH] * QUAT_REFLECT
    return out
