"""Arm Jacobian and singular values over the committed cell asset (WP-2D-02).

Forward kinematics and the geometric Jacobian only — no IK. The single IK truth stays
in ``sim.ik`` (WP-0C-02) and the single Cartesian jog in ``backend.cartesian_jog``
(WP-2D-01); this module reads the *same* MJCF asset those resolve, purely to form the
6x7 arm Jacobian that both the singularity monitor and the elbow nullspace need. It
constructs no ``Kinematics`` and solves no IK, so the ``sim.ik.staticcheck`` banned-
symbol scan holds over this tree exactly as it does over the jog's.

This mirrors ``backend.cartesian_jog.KinematicFrames``: a second reader of one asset is
not a second source of truth — the geometry here and the geometry the IK solves over
come from the one file ``sim.ik.asset`` resolves.
"""

from __future__ import annotations

import contextlib
import io

import mujoco
import numpy as np
from openarm_control.config import ArmSetup

from backend.singularity.constants import ARM_JOINTS_PER_SIDE, SIDE_WIDTH, SIDES
from sim.ik.asset import (
    EE_FRAME_TYPE,
    HOME_KEYFRAME,
    LEFT_EE_SITE,
    RIGHT_EE_SITE,
    fixed_cell_xml,
)


class ArmJacobian:
    """The 6x7 arm Jacobian and its singular values over the v2 cell asset.

    FK-only, like ``KinematicFrames``: it owns an ``ArmSetup`` (model + data) purely to
    seat a configuration and read the Jacobian of an arm's EE site. One instance serves
    one monitor or swivel on one thread; ``data`` is scratch state fully rewritten before
    each ``mj_jacSite`` call, so the order of calls does not matter. The asset is the same
    file ``sim.ik`` resolves, so this Jacobian and the IK's geometry are one source.
    """

    def __init__(self, xml: str | None = None) -> None:
        """Load the FK/Jacobian context over the fixed cell asset (or an override path).

        Args:
            xml: MJCF path; None uses the WP-0C-03 fixed cell asset. To stay one source
                with a jog, pass the same ``xml`` the jog was built with (None matches a
                default-built jog).
        """
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
        self._resolver = self._setup.joint_resolver

    def jacobian(self, side: str, arm_joints: np.ndarray) -> np.ndarray:
        """Return the 6x7 world-frame EE Jacobian of ``side`` for its seven arm joints.

        Only ``side``'s seven joints enter the returned columns. The extracted dof
        columns are partials of the EE site pose with respect to those joints, and they
        depend only on this arm's own chain and its base: the prismatic lifter translates
        the whole chain rigidly, which leaves a revolute column ``axis x (p_site - p_joint)``
        and its rotational part unchanged, and the other arm never touches this chain.
        Callers therefore pass just the jogged arm's seven joints — exactly what the jog's
        monitor hands over.

        Args:
            side: ``"right"`` or ``"left"``.
            arm_joints: The seven joint angles (radians) of that arm.

        Returns:
            (np.ndarray) The 6x7 Jacobian, translation rows over rotation rows.
        """
        side = _require_side(side)
        joints = np.asarray(arm_joints, dtype=float)
        if joints.shape[0] != ARM_JOINTS_PER_SIDE:
            raise ValueError(f"arm_joints must be {ARM_JOINTS_PER_SIDE}-dim, got {joints.shape[0]}")
        model = self._setup.model
        data = self._setup.data
        driver = np.zeros(SIDE_WIDTH, dtype=float)
        driver[:ARM_JOINTS_PER_SIDE] = joints
        self._resolver.set_qpos(data.qpos, driver, side)
        mujoco.mj_forward(model, data)
        jacp = np.zeros((3, model.nv), dtype=float)
        jacr = np.zeros((3, model.nv), dtype=float)
        mujoco.mj_jacSite(model, data, jacp, jacr, self._setup.frame_ids[side])
        dof = self._resolver.arm_dof_indices(side)
        return np.vstack([jacp[:, dof], jacr[:, dof]])

    def singular_values(self, side: str, arm_joints: np.ndarray) -> np.ndarray:
        """Return the six singular values (descending) of the 6x7 arm Jacobian."""
        return np.linalg.svd(self.jacobian(side, arm_joints), compute_uv=False)

    def nullspace_direction(self, side: str, arm_joints: np.ndarray) -> np.ndarray:
        """Return a unit self-motion direction (7-vec) with ``J @ n`` ~ 0, deterministically signed.

        A 6-DoF EE task on a 7-DoF arm has a one-dimensional Jacobian nullspace — the
        elbow self-motion. It is the right-singular vector of the smallest singular
        value. SVD fixes that vector only up to sign, so it is signed to make its
        largest-magnitude component positive: a stable convention that gives the swivel
        slider a consistent direction as long as that dominant component does not cross
        zero, which is a local property that holds along a swivel.

        Args:
            side: ``"right"`` or ``"left"``.
            arm_joints: The seven joint angles (radians) of that arm.

        Returns:
            (np.ndarray) The signed unit nullspace direction, shape (7,).
        """
        vt = np.linalg.svd(self.jacobian(side, arm_joints))[2]
        direction = np.asarray(vt[-1], dtype=float)
        dominant = int(np.argmax(np.abs(direction)))
        if direction[dominant] < 0.0:
            direction = -direction
        return direction


def _require_side(side: str) -> str:
    """Return ``side`` if it is a valid arm, else reject."""
    if side not in SIDES:
        raise ValueError(f"side must be 'right' or 'left', got {side!r}")
    return side
