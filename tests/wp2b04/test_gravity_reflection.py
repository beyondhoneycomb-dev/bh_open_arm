"""Acceptance ①: register/unregister reflects in `tau_grav`, verified by static-pose compute.

The reflection path adds the registered payload's point-mass gravity to WP-2B-02's base term.
The load-bearing test is the independent one: `tau_grav` with a payload registered must equal
what the v2 model reports when the same mass is compiled into the attachment body and its
`qfrc_bias` recomputed. That model-mutation oracle is a different method from the Jacobian
delta the model ships, so agreeing with it pins the delta's sign, frame, and magnitude — a
wrong sign would leave the shoulder term off by twice the payload torque.
"""

from __future__ import annotations

import mujoco
import numpy as np
import pytest

from backend.gravity import Arm, ArmModel, MuJoCoV2GravityBackend
from backend.gravity.constants import MJCF_V2_PATH
from backend.payload import Payload, PayloadGravityModel

_ATTACH_BODY = "openarm_right_ee_base_link"


def _mutation_oracle_tau(
    q: tuple[float, ...], mass_kg: float, cog_m: tuple[float, ...]
) -> np.ndarray:
    """Ground truth: add the payload mass to the attach body and recompute `qfrc_bias`."""
    model = mujoco.MjModel.from_xml_path(str(MJCF_V2_PATH))
    data = mujoco.MjData(model)
    attach = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, _ATTACH_BODY)
    original_mass = float(model.body_mass[attach])
    original_ipos = np.array(model.body_ipos[attach], dtype=float)
    new_mass = original_mass + mass_kg
    model.body_mass[attach] = new_mass
    model.body_ipos[attach] = (original_mass * original_ipos + mass_kg * np.array(cog_m)) / new_mass
    reference = ArmModel(Arm.RIGHT)
    data.qpos[:] = 0.0
    for index, adr in enumerate(reference.qpos_adr):
        data.qpos[adr] = q[index]
    mujoco.mj_forward(model, data)
    return np.array([data.qfrc_bias[adr] for adr in reference.dof_adr])


def test_registered_payload_moves_tau_grav(right_model: PayloadGravityModel) -> None:
    # ①: registering a payload changes tau_grav; unregistering returns it exactly.
    q = (0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1)
    base = right_model.tau_grav(q)
    right_model.registry.register(Payload.at_mount(3.0, "tool"))
    loaded = right_model.tau_grav(q)
    assert loaded != base
    assert abs(loaded[1] - base[1]) > 1.0  # the shoulder term moves materially

    right_model.registry.unregister()
    assert right_model.tau_grav(q) == base


def test_reflection_matches_model_mutation_oracle(
    right_model: PayloadGravityModel, pose_grid
) -> None:
    # ①: tau_grav with a payload equals the v2 model with the mass compiled in.
    mass, cog = 4.1, (0.02, -0.03, -0.06)
    right_model.registry.register(Payload.from_cog(mass, cog, "nominal"))
    for q in pose_grid:
        reflected = np.array(right_model.tau_grav(q))
        oracle = _mutation_oracle_tau(q, mass, cog)
        assert np.allclose(reflected, oracle, atol=1e-9), q


def test_payload_delta_zero_without_payload(right_model: PayloadGravityModel, pose_grid) -> None:
    # No registration means the delta is exactly zero — the base term is untouched.
    for q in pose_grid:
        assert right_model.payload_delta(q, None) == (0.0,) * 7
        assert right_model.tau_grav(q) == right_model.base_tau_grav(q)


def test_gravity_scale_trims_payload_delta() -> None:
    # A gravity trim scales the payload delta by the same factor as the base term.
    q = (0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1)
    payload = Payload.at_mount(3.0, "tool")

    full = PayloadGravityModel(Arm.RIGHT, backend=MuJoCoV2GravityBackend(Arm.RIGHT, 1.0))
    half = PayloadGravityModel(Arm.RIGHT, backend=MuJoCoV2GravityBackend(Arm.RIGHT, 0.5))
    full_delta = np.array(full.payload_delta(q, payload))
    half_delta = np.array(half.payload_delta(q, payload))
    assert np.allclose(half_delta, 0.5 * full_delta, atol=1e-9)


def test_pose_wrong_width_refused(right_model: PayloadGravityModel) -> None:
    from backend.payload import PayloadError

    with pytest.raises(PayloadError, match="7 entries"):
        right_model.tau_grav((0.0, 0.0, 0.0))
