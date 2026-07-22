"""Reference frames and the q_lift-reflected base transform (WP-2D-01).

A Cartesian jog is a small pose delta expressed in one of three frames — the world,
the arm's mounting base, or the tool — and the adapter must turn that frame-local
delta into a world-frame EE target the reused ``sim.ik`` solver consumes. Two facts
about the v2 cell asset shape this module:

- The arm bases ride a prismatic lifter (``openarm_lifter_joint``, travel 0–0.3 m).
  The base frame's origin in the world therefore depends on the lifter position
  ``q_lift``; ``T_world_base`` reflects it. ``sim.ik`` freezes the lifter dof and
  solves with it at zero, so the IK's world places the base at the home height. A
  world-frame target the operator reasons about must be reflected onto that IK world
  by the lifter displacement, or every command carries a systematic error up to the
  0.3 m of lifter travel (acceptance ⑤).
- The base is mounted unrotated (identity orientation at every lift), so world- and
  base-frame *deltas* coincide; the frames differ only in where their origins sit,
  which is exactly the q_lift term. That is a property of this asset, not an
  assumption — ``T_world_base`` reads the orientation back from the model.

This module owns only forward kinematics and frame geometry over the same committed
asset ``sim.ik`` resolves; it constructs no ``Kinematics`` and solves no IK. The
single IK truth stays in ``sim.ik`` (the static scan in ``sim.ik.staticcheck``
enforces that this file never reaches the banned solver symbols).
"""

from __future__ import annotations

import contextlib
import io
from enum import Enum

import mujoco
import numpy as np
from openarm_control.config import ArmSetup

from backend.cartesian_jog.constants import (
    BASE_LINK_BY_SIDE,
    BIMANUAL_WIDTH,
    INNER_FINGER_BY_SIDE,
    LIFTER_JOINT,
    SIDE_WIDTH,
)
from sim.ik.asset import (
    EE_FRAME_TYPE,
    HOME_KEYFRAME,
    LEFT_EE_SITE,
    RIGHT_EE_SITE,
    fixed_cell_xml,
)

# Pose layout shared with openarm_control: float[7] = [px, py, pz, qw, qx, qy, qz].
POSE_WIDTH = 7
QUAT_IDENTITY = np.array([1.0, 0.0, 0.0, 0.0], dtype=float)


class ReferenceFrame(Enum):
    """The frame a jog delta is expressed in.

    WORLD is the physical cell world (floor origin). BASE is the arm's mounting base,
    whose origin rides the lifter. TOOL is the current TCP frame, so a TOOL delta
    moves along the tool's own axes.
    """

    WORLD = "world"
    BASE = "base"
    TOOL = "tool"


def axis_angle_to_quat(axis: np.ndarray, angle: float) -> np.ndarray:
    """Return the unit quaternion (wxyz) rotating ``angle`` radians about ``axis``."""
    quat = np.empty(4, dtype=float)
    mujoco.mju_axisAngle2Quat(quat, np.asarray(axis, dtype=float), float(angle))
    return quat


def quat_mul(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Return the quaternion product ``left ⊗ right`` (wxyz)."""
    out = np.empty(4, dtype=float)
    mujoco.mju_mulQuat(out, np.asarray(left, dtype=float), np.asarray(right, dtype=float))
    return out


def rotate_vec(quat: np.ndarray, vec: np.ndarray) -> np.ndarray:
    """Return ``vec`` rotated by the unit quaternion ``quat`` (wxyz)."""
    out = np.empty(3, dtype=float)
    mujoco.mju_rotVecQuat(out, np.asarray(vec, dtype=float), np.asarray(quat, dtype=float))
    return out


def quat_geodesic_angle(left: np.ndarray, right: np.ndarray) -> float:
    """Return the unsigned rotation angle (radians) between two unit quaternions."""
    dot = abs(float(np.dot(np.asarray(left, dtype=float), np.asarray(right, dtype=float))))
    return 2.0 * float(np.arccos(np.clip(dot, -1.0, 1.0)))


def pose_position(pose: np.ndarray) -> np.ndarray:
    """Return the translation part of a float[7] pose."""
    return np.asarray(pose, dtype=float)[:3].copy()


def pose_quat(pose: np.ndarray) -> np.ndarray:
    """Return the orientation (wxyz) part of a float[7] pose."""
    return np.asarray(pose, dtype=float)[3:POSE_WIDTH].copy()


def make_pose(position: np.ndarray, quat: np.ndarray) -> np.ndarray:
    """Assemble a float[7] pose from a translation and an orientation (wxyz)."""
    return np.concatenate([np.asarray(position, dtype=float), np.asarray(quat, dtype=float)])


def compose_pose(outer: np.ndarray, inner: np.ndarray) -> np.ndarray:
    """Return ``outer ∘ inner`` — ``inner`` expressed in ``outer``'s parent frame."""
    position = pose_position(outer) + rotate_vec(pose_quat(outer), pose_position(inner))
    quat = quat_mul(pose_quat(outer), pose_quat(inner))
    return make_pose(position, quat)


def invert_pose(pose: np.ndarray) -> np.ndarray:
    """Return the inverse rigid transform of a float[7] pose."""
    quat_inv = np.empty(4, dtype=float)
    mujoco.mju_negQuat(quat_inv, pose_quat(pose))
    position = -rotate_vec(quat_inv, pose_position(pose))
    return make_pose(position, quat_inv)


class KinematicFrames:
    """Forward kinematics and base-frame geometry over the committed v2 cell asset.

    FK-only: it owns an ``ArmSetup`` (model + data) purely to read poses and base
    transforms, never to solve IK. One instance serves one jog adapter on one thread;
    ``_data`` is scratch state fully rewritten before every ``mj_forward``, so the
    order of calls does not matter. The asset is the same file ``sim.ik`` resolves,
    so the geometry here and the geometry the IK solves over are one source.
    """

    def __init__(self, xml: str | None = None) -> None:
        """Load the FK context over the fixed cell asset (or an override path)."""
        asset = xml if xml is not None else str(fixed_cell_xml())
        with contextlib.redirect_stdout(io.StringIO()):
            self._setup = ArmSetup.from_args(
                xml=asset,
                mode="bimanual",
                frame_right=RIGHT_EE_SITE,
                frame_type_right=EE_FRAME_TYPE,
                frame_left=LEFT_EE_SITE,
                frame_type_left=EE_FRAME_TYPE,
                keyframe=HOME_KEYFRAME,
            )
        model = self._setup.model
        lifter_jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, LIFTER_JOINT)
        if lifter_jid < 0:
            raise ValueError(f"lifter joint {LIFTER_JOINT!r} not found in the cell asset")
        self._lifter_qadr = int(model.jnt_qposadr[lifter_jid])
        self._lifter_range = (
            float(model.jnt_range[lifter_jid][0]),
            float(model.jnt_range[lifter_jid][1]),
        )

    @property
    def lifter_range(self) -> tuple[float, float]:
        """Return the lifter travel ``(lo, hi)`` in metres (the q_lift domain)."""
        return self._lifter_range

    def home_solution(self) -> np.ndarray:
        """Return the home-keyframe driver state as a float[16] right[8]+left[8] vector.

        Read from the model's ``home`` keyframe — the same rest pose ``sim.ik`` seeds
        from — so the jog's committed pose starts where the IK adapter's config does.
        """
        model = self._setup.model
        key_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, HOME_KEYFRAME)
        qpos = np.asarray(model.key_qpos[key_id] if key_id >= 0 else self._setup.data.qpos)
        right_joints, right_grip = self._setup.joint_resolver.get_driver(qpos, "right")
        left_joints, left_grip = self._setup.joint_resolver.get_driver(qpos, "left")
        return np.concatenate(
            [np.append(right_joints, float(right_grip)), np.append(left_joints, float(left_grip))]
        ).astype(float)

    def _seat(self, solution16: np.ndarray, q_lift: float) -> None:
        """Write both arms and the lifter into the scratch state, then run FK once."""
        solution = np.asarray(solution16, dtype=float)
        if solution.shape[0] != BIMANUAL_WIDTH:
            raise ValueError(f"solution must be {BIMANUAL_WIDTH}-dim, got {solution.shape[0]}")
        qpos = self._setup.data.qpos
        self._setup.joint_resolver.set_qpos(qpos, solution[:SIDE_WIDTH], "right")
        self._setup.joint_resolver.set_qpos(qpos, solution[SIDE_WIDTH:], "left")
        qpos[self._lifter_qadr] = float(q_lift)
        mujoco.mj_forward(self._setup.model, self._setup.data)

    def control_point_pose(self, side: str, solution16: np.ndarray, q_lift: float) -> np.ndarray:
        """Return the EE control-point (default TCP) world pose at this config + lift."""
        self._seat(solution16, q_lift)
        return np.asarray(self._setup.read_ee_pose(side), dtype=float)

    def world_from_base(self, side: str, q_lift: float) -> np.ndarray:
        """Return ``T_world_base`` — the arm base pose in the world at this lift.

        Read back from the model rather than assumed: the origin carries the lifter
        displacement and the orientation is whatever the asset mounts the base at.
        """
        if side not in BASE_LINK_BY_SIDE:
            raise ValueError(f"side must be 'right' or 'left', got {side!r}")
        model = self._setup.model
        data = self._setup.data
        data.qpos[self._lifter_qadr] = float(q_lift)
        mujoco.mj_forward(model, data)
        body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, BASE_LINK_BY_SIDE[side])
        return make_pose(data.xpos[body_id], data.xquat[body_id])

    def lift_offset_world(self, side: str, q_lift: float) -> np.ndarray:
        """Return the base-origin shift (world frame) between this lift and lift zero.

        This is the q_lift term of ``T_world_base``: the vector a world-frame target
        is reflected by to reach the IK world, whose base sits at lift zero.
        """
        return pose_position(self.world_from_base(side, q_lift)) - pose_position(
            self.world_from_base(side, 0.0)
        )

    def grasp_offset_pose(self, side: str) -> np.ndarray:
        """Return the control-point → grasp-point transform for this arm's gripper.

        Derived from the inner-finger body offset in the asset, so the grasp TCP is a
        real, nonzero displacement from the flange rather than a guessed constant. The
        exact fingertip is deeper and gripper-opening dependent; what acceptance ⑥
        needs is only that this offset is not identity.
        """
        self._seat(np.zeros(BIMANUAL_WIDTH), 0.0)
        model = self._setup.model
        data = self._setup.data
        finger_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, INNER_FINGER_BY_SIDE[side])
        control = self.control_point_pose(side, np.zeros(BIMANUAL_WIDTH), 0.0)
        finger_world = make_pose(data.xpos[finger_id], data.xquat[finger_id])
        # Express the finger root in the control-point frame; keep the offset on the
        # tool axis (the fingers are symmetric about it) and drop the lateral term.
        local = compose_pose(invert_pose(control), finger_world)
        offset = pose_position(local)
        offset[1] = 0.0
        return make_pose(offset, QUAT_IDENTITY)
