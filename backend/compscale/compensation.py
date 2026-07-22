"""The two torque computations: the detection model and the control feedforward.

Both read gravity and Coriolis from the one WP-2B-02 `MUJOCO_V2` backend (the single dynamics
compute point, FR-SAF-034) and add the per-joint friction torque supplied by the caller. WP-2B-09
owns no friction identification — the friction vector is `tau_fric(ω)` from WP-2B-07
(`PG-FRIC-001`, hardware-gated); this package only scales it. The two functions differ in exactly
one thing, the scale set they apply, and that is the whole point (FR-SAF-035):

* `detection_model_torque` builds its own `DetectionModelScales.full()` internally, so the
  residual observer's model is pinned to 100% and has no scale parameter a caller could
  contaminate with the control coefficient.
* `control_feedforward_torque` takes a `ControlCompensationScales` (default v1 partial:
  friction 0.3, Coriolis 0.1).

Gravity is applied at 100% in both — it is not a partial-compensation term — so the two torques
differ only in the friction and Coriolis fractions.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.compscale.errors import ScaleSeparationError
from backend.compscale.scales import (
    CompensationScales,
    ControlCompensationScales,
    DetectionModelScales,
)
from backend.dynamics.constants import ARM_JOINT_COUNT
from backend.gravity.mujoco_v2 import MuJoCoV2GravityBackend


def detection_model_torque(
    backend: MuJoCoV2GravityBackend,
    q: Sequence[float],
    qdot: Sequence[float],
    friction_tau: Sequence[float],
) -> tuple[float, ...]:
    """Return the full 100% model torque the residual observer subtracts.

    `model(q, q̇) = g(q) + C(q, q̇)·q̇ + tau_fric` with every term at full scale. This is the term
    WP-2C-01 subtracts from measured/commanded torque to isolate external torque; it takes no scale
    parameter, so it is structurally unable to run on the control feedforward's partial coefficient.

    Args:
        backend: The WP-2B-02 `MUJOCO_V2` backend for this arm.
        q: One arm's seven joint angles, v2 convention, radians.
        qdot: One arm's seven joint velocities, rad/s.
        friction_tau: One arm's seven per-joint friction torques (WP-2B-07 `tau_fric(ω)`), Nm.

    Returns:
        (tuple[float, ...]) Per-joint model torque in Nm, joint1..joint7 order.
    """
    return _compensated_torque(backend, q, qdot, friction_tau, DetectionModelScales.full())


def control_feedforward_torque(
    backend: MuJoCoV2GravityBackend,
    q: Sequence[float],
    qdot: Sequence[float],
    friction_tau: Sequence[float],
    scales: ControlCompensationScales,
) -> tuple[float, ...]:
    """Return the control feedforward torque under partial compensation.

    `g(q) + coriolis_scale·C(q, q̇)·q̇ + friction_scale·tau_fric`, with `scales` the provisional v1
    partial-compensation set (default friction 0.3, Coriolis 0.1). Gravity is full; only friction
    and Coriolis are partially compensated.

    Args:
        backend: The WP-2B-02 `MUJOCO_V2` backend for this arm.
        q: One arm's seven joint angles, v2 convention, radians.
        qdot: One arm's seven joint velocities, rad/s.
        friction_tau: One arm's seven per-joint friction torques (WP-2B-07 `tau_fric(ω)`), Nm.
        scales: The control partial-compensation scale set.

    Returns:
        (tuple[float, ...]) Per-joint feedforward torque in Nm, joint1..joint7 order.
    """
    return _compensated_torque(backend, q, qdot, friction_tau, scales)


def _compensated_torque(
    backend: MuJoCoV2GravityBackend,
    q: Sequence[float],
    qdot: Sequence[float],
    friction_tau: Sequence[float],
    scales: CompensationScales,
) -> tuple[float, ...]:
    """Compute `g + coriolis_scale·C·q̇ + friction_scale·tau_fric` under one scale set.

    The single compute point both public functions route through, parameterised by the scale set.
    Passing the scales in rather than reading a shared module value is what keeps detection and
    control on independent inputs.

    Raises:
        ScaleSeparationError: On a friction vector of the wrong width.
    """
    gravity = backend.tau_grav(q)
    coriolis = backend.tau_coriolis(q, qdot)
    friction = _checked_friction(friction_tau)
    friction_scale = scales.friction_scale
    coriolis_scale = scales.coriolis_scale
    return tuple(
        gravity[index] + coriolis_scale * coriolis[index] + friction_scale * friction[index]
        for index in range(ARM_JOINT_COUNT)
    )


def _checked_friction(friction_tau: Sequence[float]) -> tuple[float, ...]:
    """Return the friction vector as seven floats, refusing a wrong-width vector.

    Raises:
        ScaleSeparationError: If the vector is not `ARM_JOINT_COUNT` wide.
    """
    vector = tuple(float(value) for value in friction_tau)
    if len(vector) != ARM_JOINT_COUNT:
        raise ScaleSeparationError(
            f"friction vector must have {ARM_JOINT_COUNT} entries, got {len(vector)}"
        )
    return vector
