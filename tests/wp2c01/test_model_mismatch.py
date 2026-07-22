"""WP-2C-01: the residual estimates *unmodelled* torque, so a model mismatch shows up in it.

The acceptance-① harness runs plant and observer through one shared model, which makes isolation
exact — the machinery proof. This test does the opposite on purpose: it drives the plant with one
friction set and runs the observer with a different one, and shows the residual carries the
mismatch even with no external force. That is the honest boundary of this package: on hardware the
model never matches exactly, so the residual has a standing bias, which is precisely why the
per-joint thresholds are a torque-ON calibration (WP-2C-03) and why the model-error monitor
(WP-2C-09) watches the residual drift — both deferred here. A collision and a model error enter
the residual by the same door; only the calibrated threshold tells them apart.
"""

from __future__ import annotations

import numpy as np

from backend.friction import V1_SEED_FRICTION
from backend.gmo import (
    FrictionFeedforward,
    GmoModelTerms,
    MomentumObserver,
    inject_external_force,
    momentum_consistent_torque,
)
from backend.gmo.synthetic import default_trajectory

# The mismatch is well above floating-point rounding: a real model error must be visible.
_MISMATCH_FLOOR_NM = 1.0e-2


def _mismatched_model() -> GmoModelTerms:
    """A model whose friction is inflated relative to the seed the plant will use."""
    inflated = tuple(
        type(param)(f_o=param.f_o, f_v=param.f_v, f_c=param.f_c + 1.0, k_eff=param.k_eff)
        for param in V1_SEED_FRICTION
    )
    return GmoModelTerms(friction=FrictionFeedforward(inflated))


def test_friction_mismatch_biases_the_residual_without_contact(model_terms: GmoModelTerms) -> None:
    """No external force, but an observer whose friction differs from the plant sees a bias."""
    observer = MomentumObserver(_mismatched_model(), gain=90.0)
    # The plant is the shared seed model; no external force is injected.
    injection = inject_external_force(model_terms, joint=0, magnitude_nm=0.0, n_steps=400)
    observer.reset(injection.q[0], injection.qdot[0])
    residual = np.zeros(7)
    for step in range(injection.n_steps):
        residual = observer.update(
            injection.q[step], injection.qdot[step], injection.tau_meas[step], injection.dt
        )
    assert np.max(np.abs(residual)) > _MISMATCH_FLOOR_NM


def test_matched_model_has_no_bias(model_terms: GmoModelTerms) -> None:
    """The same run with the matched model leaves the residual at zero — mismatch is the cause."""
    observer = MomentumObserver(model_terms, gain=90.0)
    injection = inject_external_force(model_terms, joint=0, magnitude_nm=0.0, n_steps=400)
    observer.reset(injection.q[0], injection.qdot[0])
    residual = np.zeros(7)
    for step in range(injection.n_steps):
        residual = observer.update(
            injection.q[step], injection.qdot[step], injection.tau_meas[step], injection.dt
        )
    assert np.max(np.abs(residual)) < 1.0e-9


def test_consistent_torque_shapes_match_the_run() -> None:
    """The plant torque generator emits one measured-torque row per observer step."""
    model = GmoModelTerms()
    dt = 1.0e-3
    q, qdot = default_trajectory(51, dt)
    tau_ext = np.zeros((50, 7))
    tau_meas = momentum_consistent_torque(model, q, qdot, tau_ext, dt)
    assert tau_meas.shape == (50, 7)
