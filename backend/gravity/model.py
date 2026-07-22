"""Load the committed v2 MJCF once and expose one arm's gravity-relevant structure.

Ownership/threading: an `ArmModel` owns a private mujoco `MjData` scratch buffer and mutates
it on every evaluation, so one `ArmModel` is not safe to share across threads — each backend
holds its own and calls it from a single thread.

The v2-convention cross-check is where WP-2B-02 consumes WP-2B-01: before any gravity is
computed, the loaded model's reference (right) arm is checked against WP-2B-01's frozen v2
joint axes and joint2 range. A model failing the check is refused, because a v1-convention or
mis-axed model produces a plausible-looking but wrong shoulder gravity term (spec 12 §2.6).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import mujoco

from backend.dynamics.constants import (
    ARM_JOINT_COUNT,
    V2_JOINT2_RANGE_RAD,
    V2_JOINT_AXES,
)
from backend.gravity.backend import Arm
from backend.gravity.constants import (
    LEFT_ARM_JOINT_NAMES,
    MJCF_V2_PATH,
    RIGHT_ARM_JOINT_NAMES,
    V2_RANGE_ABS_TOL_RAD,
)
from backend.gravity.errors import GravityBackendError

_AXIS_ABS_TOL = 1.0e-6


class ArmModel:
    """The committed v2 model plus one arm's joint indices and distal-body subtrees.

    Attributes:
        arm: The arm this handle addresses.
        model: The compiled mujoco model for the committed v2 bimanual MJCF.
        data: A private scratch buffer mutated on every pose evaluation.
        joint_ids: The seven arm joint ids, joint1..joint7 order.
        qpos_adr: Each arm joint's index into `data.qpos`.
        dof_adr: Each arm joint's index into `data.qvel` / `data.qfrc_bias`.
        subtrees: Each arm joint's distal body ids (the bodies gravity on that joint sums over).
    """

    def __init__(self, arm: Arm) -> None:
        """Load the v2 model, resolve the arm's joint layout, and verify the v2 convention.

        Raises:
            GravityBackendError: If a joint name is absent, or the model fails the v2 check.
        """
        self.arm = arm
        self.model = mujoco.MjModel.from_xml_path(str(MJCF_V2_PATH))
        self.data = mujoco.MjData(self.model)
        names = RIGHT_ARM_JOINT_NAMES if arm is Arm.RIGHT else LEFT_ARM_JOINT_NAMES
        self.joint_ids = tuple(self._joint_id(name) for name in names)
        self.qpos_adr = tuple(int(self.model.jnt_qposadr[j]) for j in self.joint_ids)
        self.dof_adr = tuple(int(self.model.jnt_dofadr[j]) for j in self.joint_ids)
        self.subtrees = tuple(self._subtree(int(self.model.jnt_bodyid[j])) for j in self.joint_ids)
        _verify_v2_convention(self.model)

    def _joint_id(self, name: str) -> int:
        """Return a joint's id, refusing a name the model does not define."""
        joint_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)
        if joint_id < 0:
            raise GravityBackendError(f"joint {name!r} is absent from {MJCF_V2_PATH.name}")
        return int(joint_id)

    def _subtree(self, root_body: int) -> frozenset[int]:
        """Return `root_body` and every body below it, following `body_parentid`.

        Gravity on a joint sums over exactly the bodies distal to it, so this set — computed
        once from the static tree — is the summation domain for that joint (fingers and the
        end-effector below the wrist included).
        """
        members = {root_body}
        for body in range(self.model.nbody):
            ancestor = body
            while ancestor != 0:
                ancestor = int(self.model.body_parentid[ancestor])
                if ancestor == root_body:
                    members.add(body)
                    break
        return frozenset(members)

    def set_pose(self, q: Sequence[float], qdot: Sequence[float] | None = None) -> None:
        """Write one arm's pose into the scratch buffer, zeroing every other joint.

        The two arms are independent subtrees rooted at the world, so the gravity of this arm
        does not depend on the other's pose; zeroing the rest is for determinism, not physics.

        Args:
            q: The arm's seven joint angles, radians.
            qdot: The arm's seven joint velocities, rad/s, or None to leave them at zero.

        Raises:
            GravityBackendError: On a joint vector of the wrong width.
        """
        angles = _checked(q)
        self.data.qpos[:] = 0.0
        self.data.qvel[:] = 0.0
        for index, adr in enumerate(self.qpos_adr):
            self.data.qpos[adr] = angles[index]
        if qdot is not None:
            rates = _checked(qdot)
            for index, adr in enumerate(self.dof_adr):
                self.data.qvel[adr] = rates[index]

    def arm_dofs(self, dof_vector: Sequence[float]) -> tuple[float, ...]:
        """Pick this arm's seven entries out of a full per-dof vector (e.g. `qfrc_bias`)."""
        return tuple(float(dof_vector[adr]) for adr in self.dof_adr)


def _checked(values: Sequence[float]) -> tuple[float, ...]:
    """Return `values` as a seven-float tuple, refusing a wrong-width joint vector.

    Raises:
        GravityBackendError: If the vector is not `ARM_JOINT_COUNT` wide.
    """
    vector = tuple(float(value) for value in values)
    if len(vector) != ARM_JOINT_COUNT:
        raise GravityBackendError(
            f"joint vector must have {ARM_JOINT_COUNT} entries, got {len(vector)}"
        )
    return vector


def _verify_v2_convention(model: mujoco.MjModel) -> None:
    """Refuse a model whose reference arm is not in WP-2B-01's frozen v2 joint convention.

    The right arm is the arm WP-2B-01 froze `V2_JOINT_AXES` and `V2_JOINT2_RANGE_RAD` against,
    so it is the reference regardless of which arm a backend later computes. A mismatch means
    the asset is not the v2 model this package must compute gravity on (spec 12 §2.6).

    Raises:
        GravityBackendError: On an absent reference joint, a wrong axis, or a joint2 range that
            is not the v2 endpoints.
    """
    for index, name in enumerate(RIGHT_ARM_JOINT_NAMES):
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        if joint_id < 0:
            raise GravityBackendError(f"reference joint {name!r} is absent from the v2 model")
        axis = tuple(float(component) for component in model.jnt_axis[joint_id])
        expected = V2_JOINT_AXES[index]
        if any(abs(axis[k] - expected[k]) > _AXIS_ABS_TOL for k in range(3)):
            raise GravityBackendError(
                f"{name} axis {axis} does not match the v2 reference {expected} "
                "(model is not in the v2 joint convention)"
            )
    j2_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "openarm_right_joint2")
    low = float(model.jnt_range[j2_id][0])
    high = float(model.jnt_range[j2_id][1])
    if not (
        math.isclose(low, V2_JOINT2_RANGE_RAD[0], abs_tol=V2_RANGE_ABS_TOL_RAD)
        and math.isclose(high, V2_JOINT2_RANGE_RAD[1], abs_tol=V2_RANGE_ABS_TOL_RAD)
    ):
        raise GravityBackendError(
            f"joint2 range ({low}, {high}) is not the v2 convention {V2_JOINT2_RANGE_RAD} "
            "(a v1-convention model would differ by ~pi/2 and mis-compute shoulder gravity)"
        )
