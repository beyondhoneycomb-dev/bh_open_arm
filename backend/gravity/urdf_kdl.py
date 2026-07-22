"""The `URDF_KDL` backend: gravity from the KDL potential-energy projection, not `qfrc_bias`.

FR-SAF-034 names this the legacy path — the v1 `Dynamics::GetGravity` family, which parses a
URDF and computes gravity with a KDL recursive solver. No standalone v1 URDF + KDL toolchain
is present on this host, so this backend computes the identical KDL result — the gravity
generalized force `τ_j = Σ_i m_i · (a_j × (c_i − p_j)) · g` summed over the bodies distal to
each joint — over the committed v2 model's forward kinematics, which is exactly what a URDF's
kinematic tree supplies. It is genuinely independent of `MUJOCO_V2`: it reads only forward
kinematics (`mj_kinematics`) and per-body mass, and never the model's `qfrc_bias`.

Gravity depends only on mass and centre-of-mass position, not the inertia tensor, so with the
inertial source read from the v2 model this reproduces `MUJOCO_V2` to machine precision — the
cross-check WP-2B-02 acceptance ① tables. The source is a constructor argument precisely so an
independent v1-URDF inertia set can be substituted to quantify the FR-SAF-034 negative-branch
gap ("KDL re-implementation does not reflect v2 inertia") without editing this file.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import mujoco
import numpy as np

from backend.gravity.backend import Arm, BackendId, GravityBackend
from backend.gravity.constants import GRAVITY_SCALE_DEFAULT
from backend.gravity.model import ArmModel


@dataclass(frozen=True)
class InertialParams:
    """A per-body mass vector, indexed by mujoco body id — the inertia source gravity reads.

    Default construction (`from_model`) reads the committed v2 model, so the KDL backend
    reflects v2 inertia. An alternate vector substitutes an independent inertia (a v1 URDF's
    masses) to make the FR-SAF-034 negative-branch gap measurable against `MUJOCO_V2`.

    Attributes:
        body_mass: Mass in kg per mujoco body id, length `model.nbody`.
    """

    body_mass: tuple[float, ...]

    @classmethod
    def from_model(cls, model: mujoco.MjModel) -> InertialParams:
        """Read the per-body mass vector from a compiled model (the v2-inertia source)."""
        return cls(tuple(float(mass) for mass in model.body_mass))


class UrdfKdlGravityBackend(GravityBackend):
    """Gravity for one arm via the KDL potential-energy projection over the model's kinematics.

    This backend computes gravity only. Coriolis and centrifugal terms need a full velocity
    solve, which the legacy KDL gravity path does not provide and which is `MUJOCO_V2`'s job;
    see spec 12 §2.6, which recommends `MUJOCO_V2` as the canonical backend.
    """

    def __init__(
        self,
        arm: Arm = Arm.RIGHT,
        gravity_scale: float = GRAVITY_SCALE_DEFAULT,
        inertial_params: InertialParams | None = None,
    ) -> None:
        """Build the backend, loading the v2 model and defaulting inertia to v2 masses."""
        super().__init__(arm, gravity_scale)
        self._model = ArmModel(arm)
        self._inertia = inertial_params or InertialParams.from_model(self._model.model)

    @property
    def backend_id(self) -> BackendId:
        """This backend's selector value."""
        return BackendId.URDF_KDL

    def tau_grav(self, q: Sequence[float]) -> tuple[float, ...]:
        """Return the gravity torque via the CoM Jacobian projection, scaled by `gravity_scale`.

        Args:
            q: One arm's seven joint angles, v2 convention, radians.

        Returns:
            (tuple[float, ...]) Per-joint gravity torque in Nm, joint1..joint7 order.
        """
        model = self._model
        model.set_pose(q)
        mujoco.mj_kinematics(model.model, model.data)
        gravity_vec = np.asarray(model.model.opt.gravity, dtype=float)
        mass = self._inertia.body_mass
        torques: list[float] = []
        for index, joint_id in enumerate(model.joint_ids):
            axis = np.asarray(model.data.xaxis[joint_id], dtype=float)
            anchor = np.asarray(model.data.xanchor[joint_id], dtype=float)
            torque = 0.0
            for body in model.subtrees[index]:
                lever = np.asarray(model.data.xipos[body], dtype=float) - anchor
                torque -= mass[body] * float(np.dot(gravity_vec, np.cross(axis, lever)))
            torques.append(self._gravity_scale * torque)
        return tuple(torques)
