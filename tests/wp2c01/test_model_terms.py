"""WP-2C-01: the observer's model terms are the reused primitives plus the added inertia.

The mass matrix is the one dynamics quantity WP-2C-01 adds; gravity, Coriolis, and friction are
reused from WP-2B-02 and WP-2B-07. These tests check the added inertia is a valid mass matrix
(symmetric positive-definite), that the momentum is `M(q)*q_dot`, and that the model terms hand
back exactly what the reused packages compute — no re-implementation drifted in.
"""

from __future__ import annotations

import numpy as np

from backend.friction import V1_SEED_FRICTION
from backend.gmo import FrictionFeedforward, GmoModelTerms, MassMatrix
from backend.gravity import Arm, MuJoCoV2GravityBackend

_POSES = (
    (0.0, 0.3, 0.0, 0.4, 0.0, 0.0, 0.0),
    (0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1),
    (-0.5, 0.2, 0.9, 1.5, -0.7, 0.4, -1.0),
)
_RATES = (
    (0.2, -0.1, 0.3, 0.05, -0.2, 0.1, 0.0),
    (-0.4, 0.3, -0.2, 0.6, 0.1, -0.5, 0.2),
)


def test_mass_matrix_is_symmetric_positive_definite() -> None:
    """`M(q)` is a valid inertia matrix at every test pose."""
    mass = MassMatrix(Arm.RIGHT)
    for pose in _POSES:
        inertia = mass.inertia(pose)
        assert inertia.shape == (7, 7)
        assert np.allclose(inertia, inertia.T)
        assert np.all(np.linalg.eigvalsh(inertia) > 0.0)


def test_momentum_is_inertia_times_velocity() -> None:
    """The generalized momentum is exactly `M(q)*q_dot`."""
    mass = MassMatrix(Arm.RIGHT)
    for pose in _POSES:
        for rate in _RATES:
            expected = mass.inertia(pose) @ np.asarray(rate)
            assert np.allclose(mass.momentum(pose, rate), expected)


def test_model_terms_reuse_gravity_backend(model_terms: GmoModelTerms) -> None:
    """`gravity` and `coriolis` return exactly what the reused WP-2B-02 backend computes."""
    backend = MuJoCoV2GravityBackend(Arm.RIGHT)
    for pose in _POSES:
        assert np.allclose(model_terms.gravity(pose), backend.tau_grav(pose))
        for rate in _RATES:
            assert np.allclose(model_terms.coriolis(pose, rate), backend.tau_coriolis(pose, rate))


def test_model_terms_reuse_friction(model_terms: GmoModelTerms) -> None:
    """`friction` returns exactly the reused WP-2B-07 tanh law at the seed parameters."""
    for rate in _RATES:
        expected = np.array(
            [
                float(param.tau(np.array([w]))[0])
                for param, w in zip(V1_SEED_FRICTION, rate, strict=True)
            ]
        )
        assert np.allclose(model_terms.friction(rate), expected)


def test_beta_is_the_signed_sum_of_the_terms(model_terms: GmoModelTerms) -> None:
    """The integrand model part is `tau_meas + coriolis - gravity - friction`."""
    pose = _POSES[1]
    rate = _RATES[0]
    tau_meas = np.array([1.0, -2.0, 0.5, 3.0, -0.7, 0.2, 0.1])
    expected = (
        tau_meas
        + model_terms.coriolis(pose, rate)
        - model_terms.gravity(pose)
        - model_terms.friction(rate)
    )
    assert np.allclose(model_terms.beta(pose, rate, tau_meas), expected)


def test_friction_feedforward_accepts_identified_params() -> None:
    """A model built from an explicit friction set uses it, not the seed default."""
    scaled = tuple(
        type(param)(f_o=param.f_o * 2.0, f_v=param.f_v, f_c=param.f_c, k_eff=param.k_eff)
        for param in V1_SEED_FRICTION
    )
    model = GmoModelTerms.from_friction_params(scaled)
    rate = _RATES[1]
    expected = FrictionFeedforward(scaled).friction(rate)
    assert np.allclose(model.friction(rate), expected)
    assert not np.allclose(model.friction(rate), FrictionFeedforward().friction(rate))
