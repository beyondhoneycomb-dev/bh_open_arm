"""The inverse-dynamics basis subtracted to expose friction: `M(q)*qdd + C(q,qd)*qd + g(q)`.

Friction is what is left of the measured joint torque after the rigid-body dynamics are
removed. This module computes that rigid-body term and, critically, keeps its three
contributions apart so the fit residual can be tested for separation from each (acceptance ①,
§2.0): a friction fit that has quietly absorbed a gravity or inertia error still shows that
error as a correlation between the post-fit residual and the corresponding signal.

Two ownership facts hold this module honest:

* Gravity `g(q)` and Coriolis `C*qd` come from WP-2B-02's `MuJoCoV2GravityBackend`, the single
  gravity compute point (FR-SAF-034). This package does not re-derive gravity; it consumes it.
* The inertia term `M(q)*qdd` is the one contribution WP-2B-02 does not expose, so it is
  computed here from the same committed v2 model via the full mass matrix (armature included,
  because reflected rotor inertia is a real torque the motor must overcome).

The basis is a function of `q`, `qd`, `qdd` only — never of any friction parameter. The thing
subtracted to reveal the friction result therefore cannot depend on that result, so the fit is
free of the self-approval an own-result-fed basis would introduce.
"""

from __future__ import annotations

from dataclasses import dataclass

import mujoco
import numpy as np
from numpy.typing import NDArray

from backend.friction.constants import ARM_JOINT_COUNT
from backend.friction.errors import FrictionIdentificationError
from backend.friction.log import ExcitationLog
from backend.gravity import Arm, ArmModel, MuJoCoV2GravityBackend

# The basis must subtract the full modelled gravity, not a runtime-trimmed value: a
# `gravity_scale` below 1.0 would leave a fraction of gravity in the residual for the friction
# fit to absorb. Identification always runs at unit gravity.
_FULL_GRAVITY_SCALE = 1.0


@dataclass(frozen=True)
class DynamicsComponents:
    """The rigid-body model torque of an excitation log, split by contribution.

    Each array is `(n_samples, ARM_JOINT_COUNT)`, joint1..joint7 order, Nm.

    Attributes:
        gravity: The gravity term `g(q)` per sample.
        coriolis: The Coriolis and centrifugal term `C(q,qd)*qd` per sample.
        inertia: The inertia term `M(q)*qdd` per sample.
        total: `gravity + coriolis + inertia`, the full rigid-body model torque.
    """

    gravity: NDArray[np.float64]
    coriolis: NDArray[np.float64]
    inertia: NDArray[np.float64]
    total: NDArray[np.float64]

    def friction_residual(self, tau: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return `tau - total`: the measured torque with the rigid-body model removed.

        Args:
            tau: Measured joint torque, `(n_samples, ARM_JOINT_COUNT)`, Nm.

        Returns:
            (NDArray[np.float64]) The friction residual per sample and joint, Nm.
        """
        return tau - self.total


class InverseDynamicsBasis:
    """Compute `M*qdd + C*qd + g` for one arm from the committed v2 model.

    Ownership/threading: this holds a `MuJoCoV2GravityBackend` and a private `ArmModel`, each
    owning a mujoco scratch buffer mutated on every call, so one basis is used from one thread.
    """

    def __init__(self, arm: Arm) -> None:
        """Build the gravity backend and inertia model for `arm` at unit gravity."""
        self._arm = arm
        self._gravity = MuJoCoV2GravityBackend(arm=arm, gravity_scale=_FULL_GRAVITY_SCALE)
        self._inertia_model = ArmModel(arm)
        nv = self._inertia_model.model.nv
        self._full_mass = np.zeros((nv, nv), dtype=np.float64)
        self._qacc = np.zeros(nv, dtype=np.float64)

    def _inertia_torque(
        self, q: NDArray[np.float64], qdd: NDArray[np.float64]
    ) -> tuple[float, ...]:
        """Return `M(q)*qdd` for the arm's joints via the full mass matrix.

        Args:
            q: One arm's seven joint angles, v2 convention, radians.
            qdd: One arm's seven joint accelerations, rad/s^2.

        Returns:
            (tuple[float, ...]) Per-joint inertia torque, Nm, joint1..joint7 order.
        """
        model = self._inertia_model
        model.set_pose(q)
        mujoco.mj_forward(model.model, model.data)
        mujoco.mj_fullM(model.model, model.data, self._full_mass)
        self._qacc[:] = 0.0
        for index, adr in enumerate(model.dof_adr):
            self._qacc[adr] = float(qdd[index])
        generalized = self._full_mass @ self._qacc
        return model.arm_dofs(generalized)

    def evaluate(self, log: ExcitationLog) -> DynamicsComponents:
        """Compute the split rigid-body model torque for every sample of an excitation log.

        Args:
            log: The excitation log to evaluate against.

        Returns:
            (DynamicsComponents) Gravity, Coriolis, inertia and total torque per sample.

        Raises:
            FrictionIdentificationError: On an empty log, which has no dynamics to evaluate.
        """
        if log.n_samples == 0:
            raise FrictionIdentificationError("cannot evaluate the basis on an empty log")
        n = log.n_samples
        gravity = np.zeros((n, ARM_JOINT_COUNT), dtype=np.float64)
        coriolis = np.zeros((n, ARM_JOINT_COUNT), dtype=np.float64)
        inertia = np.zeros((n, ARM_JOINT_COUNT), dtype=np.float64)
        for sample in range(n):
            q = log.q[sample]
            qd = log.qd[sample]
            qdd = log.qdd[sample]
            gravity[sample] = self._gravity.tau_grav(q)
            coriolis[sample] = self._gravity.tau_coriolis(q, qd)
            inertia[sample] = self._inertia_torque(q, qdd)
        total = gravity + coriolis + inertia
        return DynamicsComponents(gravity=gravity, coriolis=coriolis, inertia=inertia, total=total)
