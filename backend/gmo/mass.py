"""The joint-space inertia matrix `M(q)` and the generalized momentum `p = M(q)*q_dot`.

The momentum observer is built on the generalized momentum, and no reused package exposes it:
`backend.gravity` computes gravity and Coriolis but not the mass matrix. So this module owns the
one dynamics quantity WP-2C-01 must add — `M(q)` — while still reusing WP-2B-02's model load:
`ArmModel` already loads the committed v2 MJCF, verifies the v2 joint convention, and resolves
one arm's DOF addresses. Loading it here reuses that verified handle rather than opening a second,
unverified view of the asset; mujoco's `mj_fullM` then densifies the inertia and this slices the
arm's seven DOFs out of the bimanual model.

Ownership/threading: an instance owns a private `ArmModel` scratch buffer mutated on every call,
so one `MassMatrix` is used from one thread — the actuation loop that drives the observer.
"""

from __future__ import annotations

from collections.abc import Sequence

import mujoco
import numpy as np
from numpy.typing import NDArray

from backend.gmo.constants import GMO_JOINT_COUNT
from backend.gmo.errors import GmoJointCountError
from backend.gravity import ArmModel
from backend.gravity.backend import Arm


class MassMatrix:
    """One arm's joint-space inertia `M(q)`, read from the committed v2 model."""

    def __init__(self, arm: Arm = Arm.RIGHT) -> None:
        """Load the v2 model for `arm` (verifying its v2 convention) and size its dense buffer."""
        self._model = ArmModel(arm)
        self._dof_adr = np.asarray(self._model.dof_adr, dtype=np.intp)
        self._dense = np.zeros((self._model.model.nv, self._model.model.nv), dtype=np.float64)

    @property
    def arm(self) -> Arm:
        """The arm this mass matrix computes for."""
        return self._model.arm

    def inertia(self, q: Sequence[float]) -> NDArray[np.float64]:
        """Return the arm's 7x7 joint-space inertia `M(q)`.

        Args:
            q: One arm's seven joint angles, v2 convention, radians.

        Returns:
            (NDArray[np.float64]) The symmetric positive-definite `M(q)`, joint1..joint7 order.

        Raises:
            GmoJointCountError: On a joint vector of the wrong width.
        """
        self._checked(q)
        self._model.set_pose(q)
        mujoco.mj_forward(self._model.model, self._model.data)
        mujoco.mj_fullM(self._model.model, self._model.data, self._dense)
        return self._dense[np.ix_(self._dof_adr, self._dof_adr)].copy()

    def momentum(self, q: Sequence[float], qdot: Sequence[float]) -> NDArray[np.float64]:
        """Return the generalized momentum `p = M(q)*q_dot`.

        Args:
            q: One arm's seven joint angles, v2 convention, radians.
            qdot: One arm's seven joint velocities, rad/s.

        Returns:
            (NDArray[np.float64]) Per-joint momentum, Nm*s, joint1..joint7 order.

        Raises:
            GmoJointCountError: On a joint vector of the wrong width.
        """
        rates = self._checked(qdot)
        return self.inertia(q) @ rates

    def _checked(self, values: Sequence[float]) -> NDArray[np.float64]:
        """Return `values` as a length-`GMO_JOINT_COUNT` array, refusing a wrong width.

        Raises:
            GmoJointCountError: If the vector is not `GMO_JOINT_COUNT` wide.
        """
        vector = np.asarray(values, dtype=np.float64)
        if vector.shape != (GMO_JOINT_COUNT,):
            raise GmoJointCountError(
                f"joint vector must have {GMO_JOINT_COUNT} entries, got shape {vector.shape}"
            )
        return vector
