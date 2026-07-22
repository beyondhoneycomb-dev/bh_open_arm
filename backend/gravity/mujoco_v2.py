"""The default `MUJOCO_V2` backend: gravity and Coriolis from the v2 model's `qfrc_bias`.

FR-SAF-034 makes this the default because it uses v2 inertia directly: spec 12 §2.6 path B is
"load the v2 MJCF, read `data.qfrc_bias` for gravity+Coriolis on v2 inertia". mujoco's
`qfrc_bias` is the recursive-Newton-Euler bias `C(q, q̇)·q̇ + g(q)` and excludes actuator,
constraint and passive (spring/damper/frictionloss) forces, so at zero velocity it is exactly
the gravity term.

`gravity_scale` trims only the gravity part: the combined bias is `full − g + scale·g`, so the
Coriolis contribution is never scaled by a gravity trim. `tau_coriolis` exposes `C·q̇` alone
for the GMO's `Ĉᵀq̇` term (WP-2C-01).
"""

from __future__ import annotations

from collections.abc import Sequence

import mujoco

from backend.gravity.backend import Arm, BackendId, GravityBackend
from backend.gravity.constants import GRAVITY_SCALE_DEFAULT
from backend.gravity.model import ArmModel


class MuJoCoV2GravityBackend(GravityBackend):
    """Gravity and Coriolis for one arm, read from the committed v2 model's bias force."""

    def __init__(self, arm: Arm = Arm.RIGHT, gravity_scale: float = GRAVITY_SCALE_DEFAULT) -> None:
        """Build the backend and load the v2 model for `arm` (verifying its v2 convention)."""
        super().__init__(arm, gravity_scale)
        self._model = ArmModel(arm)

    @property
    def backend_id(self) -> BackendId:
        """This backend's selector value."""
        return BackendId.MUJOCO_V2

    def tau_grav(self, q: Sequence[float]) -> tuple[float, ...]:
        """Return the gravity torque at zero velocity, scaled by `gravity_scale`.

        Args:
            q: One arm's seven joint angles, v2 convention, radians.

        Returns:
            (tuple[float, ...]) Per-joint gravity torque in Nm, joint1..joint7 order.
        """
        gravity = self._gravity_unscaled(q)
        return tuple(self._gravity_scale * torque for torque in gravity)

    def tau_bias(self, q: Sequence[float], qdot: Sequence[float]) -> tuple[float, ...]:
        """Return `C(q, q̇)·q̇ + scale·g(q)` — gravity (trimmed) plus Coriolis and centrifugal.

        Args:
            q: One arm's seven joint angles, v2 convention, radians.
            qdot: One arm's seven joint velocities, rad/s.

        Returns:
            (tuple[float, ...]) Per-joint bias torque in Nm, joint1..joint7 order.
        """
        gravity = self._gravity_unscaled(q)
        self._model.set_pose(q, qdot)
        mujoco.mj_forward(self._model.model, self._model.data)
        full = self._model.arm_dofs(self._model.data.qfrc_bias)
        return tuple(
            full[index] + (self._gravity_scale - 1.0) * gravity[index] for index in range(len(full))
        )

    def tau_coriolis(self, q: Sequence[float], qdot: Sequence[float]) -> tuple[float, ...]:
        """Return the Coriolis and centrifugal torque `C(q, q̇)·q̇` alone (no gravity trim).

        Args:
            q: One arm's seven joint angles, v2 convention, radians.
            qdot: One arm's seven joint velocities, rad/s.

        Returns:
            (tuple[float, ...]) Per-joint Coriolis+centrifugal torque in Nm, joint1..joint7.
        """
        gravity = self._gravity_unscaled(q)
        self._model.set_pose(q, qdot)
        mujoco.mj_forward(self._model.model, self._model.data)
        full = self._model.arm_dofs(self._model.data.qfrc_bias)
        return tuple(full[index] - gravity[index] for index in range(len(full)))

    def _gravity_unscaled(self, q: Sequence[float]) -> tuple[float, ...]:
        """Return the raw gravity torque `g(q)` (bias at zero velocity), before any trim."""
        self._model.set_pose(q)
        mujoco.mj_forward(self._model.model, self._model.data)
        return self._model.arm_dofs(self._model.data.qfrc_bias)
