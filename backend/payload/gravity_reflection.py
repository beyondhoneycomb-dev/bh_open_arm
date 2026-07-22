"""Reflect a registered payload into the WP-2B-02 gravity torque.

FR-SAF-036/FR-MAN-033 require a registered payload to appear in the gravity-compensation
model. This module is that reflection path: the base gravity comes from WP-2B-02's single
`tau_grav(q)` compute point (consumed through the FR-SAF-034 selector), and the payload adds
a delta on top, so WP-2B-02 stays the one source of the arm's own gravity while the payload
contribution is an explicit, testable increment.

A payload registered at the end-effector is, for gravity, a point mass at its centre of
gravity — at zero velocity gravity torque depends only on mass and CoM position, not on the
payload's rotational inertia, so a point-mass model is exact for this term. The delta is the
gravity generalised force of that point mass, `-J_p^T (m * g)` restricted to the arm's seven
dofs, where `J_p` is the translational Jacobian of the CoG point on the attachment body and
`g` is the model's own gravity vector. The sign is fixed against the model-mutation ground
truth (add the mass to the body, recompute `qfrc_bias`) by the acceptance test, so the sum
equals what the v2 model would report with the payload compiled in.

Ownership/threading: this model owns a private mujoco scratch buffer (its own `ArmModel`) and
the injected WP-2B-02 backend owns another; both are mutated per call, so one model is used
from one thread. Build one per consumer.
"""

from __future__ import annotations

from collections.abc import Sequence

import mujoco
import numpy as np

from backend.dynamics.constants import ARM_JOINT_COUNT
from backend.gravity import Arm, ArmModel, BackendId, GravityBackend, select_backend
from backend.payload.constants import EE_ATTACH_BODY_TEMPLATE
from backend.payload.errors import PayloadError
from backend.payload.payload import Payload
from backend.payload.registry import PayloadRegistry

_JACOBIAN_ROWS = 3


class PayloadGravityModel:
    """Gravity torque for one arm with the registered payload reflected in.

    Attributes:
        arm: The arm this model computes for.
        registry: The payload registry this model reads; register/unregister through it and
            the next `tau_grav` reflects the change.
    """

    def __init__(
        self,
        arm: Arm,
        backend: GravityBackend | None = None,
        registry: PayloadRegistry | None = None,
    ) -> None:
        """Build the reflection over a WP-2B-02 backend and a private model for the Jacobian.

        Args:
            arm: The arm to compute for.
            backend: The WP-2B-02 gravity backend supplying the base `tau_grav`. Defaults to
                the FR-SAF-034 selector's `MUJOCO_V2` backend for `arm`.
            registry: The payload registry to read. Defaults to a fresh empty registry.

        Raises:
            PayloadError: If an injected backend computes for a different arm, or the
                attachment body is absent from the model.
        """
        self.arm = arm
        self.registry = registry if registry is not None else PayloadRegistry()
        self._backend = backend if backend is not None else select_backend(BackendId.MUJOCO_V2, arm)
        if self._backend.arm is not arm:
            raise PayloadError(f"injected backend computes for {self._backend.arm}, not {arm}")
        self._model = ArmModel(arm)
        body_name = EE_ATTACH_BODY_TEMPLATE.format(side=arm.value)
        attach = mujoco.mj_name2id(self._model.model, mujoco.mjtObj.mjOBJ_BODY, body_name)
        if attach < 0:
            raise PayloadError(f"attachment body {body_name!r} is absent from the v2 model")
        self._attach_body = int(attach)
        self._gravity_vec = np.array(self._model.model.opt.gravity, dtype=float)

    def payload_delta(self, q: Sequence[float], payload: Payload | None) -> tuple[float, ...]:
        """Return the per-joint gravity torque a payload adds at pose `q` (zeros if none).

        Args:
            q: The arm's seven joint angles, v2 convention, radians.
            payload: The payload to reflect, or None for no payload.

        Returns:
            (tuple[float, ...]) Per-joint payload gravity torque, Nm, joint1..joint7 order,
            trimmed by the backend's `gravity_scale` so it matches the base term.

        Raises:
            PayloadError: On a joint vector of the wrong width.
        """
        pose = self._checked_pose(q)
        if payload is None:
            return (0.0,) * ARM_JOINT_COUNT
        self._model.set_pose(pose)
        mujoco.mj_forward(self._model.model, self._model.data)
        origin = np.array(self._model.data.xpos[self._attach_body], dtype=float)
        rotation = np.array(self._model.data.xmat[self._attach_body], dtype=float).reshape(3, 3)
        point = origin + rotation @ np.array(payload.cog_m, dtype=float)
        jacp = np.zeros((_JACOBIAN_ROWS, self._model.model.nv), dtype=float)
        jacr = np.zeros((_JACOBIAN_ROWS, self._model.model.nv), dtype=float)
        mujoco.mj_jac(self._model.model, self._model.data, jacp, jacr, point, self._attach_body)
        # `-J_p^T (m g)` is the payload's gravity generalised force in the qfrc_bias
        # convention the base term uses; the acceptance test pins this sign against the
        # model-mutation ground truth. Trim by the same gravity_scale as the base.
        full = -(jacp.T @ (payload.mass_kg * self._gravity_vec)) * self._backend.gravity_scale
        return tuple(float(full[adr]) for adr in self._model.dof_adr)

    def tau_grav(self, q: Sequence[float]) -> tuple[float, ...]:
        """Return the gravity torque with the registered payload reflected in.

        The base term is WP-2B-02's `tau_grav(q)`; the registered payload's delta is added
        to it. With nothing registered this is exactly the base term, so registering and
        unregistering move `tau_grav` by exactly the payload contribution (acceptance ①).

        Args:
            q: The arm's seven joint angles, v2 convention, radians.

        Returns:
            (tuple[float, ...]) Per-joint gravity torque, Nm, joint1..joint7 order.

        Raises:
            PayloadError: On a joint vector of the wrong width.
        """
        pose = self._checked_pose(q)
        base = self._backend.tau_grav(pose)
        delta = self.payload_delta(pose, self.registry.current())
        return tuple(base[index] + delta[index] for index in range(ARM_JOINT_COUNT))

    def base_tau_grav(self, q: Sequence[float]) -> tuple[float, ...]:
        """Return the arm's own gravity torque without any payload (the WP-2B-02 base term).

        Args:
            q: The arm's seven joint angles, v2 convention, radians.

        Returns:
            (tuple[float, ...]) Per-joint gravity torque with no payload, Nm.

        Raises:
            PayloadError: On a joint vector of the wrong width.
        """
        return self._backend.tau_grav(self._checked_pose(q))

    @property
    def gravity_scale(self) -> float:
        """The gravity trim the base backend applies (and this model applies to the payload)."""
        return self._backend.gravity_scale

    def _checked_pose(self, q: Sequence[float]) -> tuple[float, ...]:
        """Return `q` as a seven-float tuple, refusing a wrong-width joint vector.

        Raises:
            PayloadError: If the vector is not `ARM_JOINT_COUNT` wide.
        """
        pose = tuple(float(value) for value in q)
        if len(pose) != ARM_JOINT_COUNT:
            raise PayloadError(f"joint vector must have {ARM_JOINT_COUNT} entries, got {len(pose)}")
        return pose
