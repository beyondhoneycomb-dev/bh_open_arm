"""WP-2C-01 acceptance ①: a synthetic external force makes the residual respond and isolate.

The plant is consistent with the observer's model (see `backend.gmo.synthetic`), so the residual
recovers the injected external torque and stays at zero on the untouched joints — proving the
observer machinery integrates, feeds back, and isolates by joint. Hardware model-mismatch is a
deferred calibration, not exercised here.
"""

from __future__ import annotations

import numpy as np

from backend.gmo import (
    GmoModelTerms,
    MomentumObserver,
    inject_external_force,
    isolate_joints,
)

# The residual reaches the injected torque to within this fraction after enough steps for the
# first-order response (gain * dt * steps >> 1). The tracking is exact in the consistent plant;
# the tolerance only covers the geometric approach to the step.
_TRACKING_TOL_NM = 1.0e-3
# A joint the injection never touched must stay flat to floating-point rounding.
_QUIET_JOINT_TOL_NM = 1.0e-9


def _run(model: GmoModelTerms, joint: int, magnitude_nm: float, gain: float = 90.0) -> np.ndarray:
    """Drive the observer through an injection on `joint` and return the final residual."""
    observer = MomentumObserver(model, gain=gain)
    injection = inject_external_force(model, joint=joint, magnitude_nm=magnitude_nm, n_steps=500)
    observer.reset(injection.q[0], injection.qdot[0])
    residual = np.zeros(7)
    for step in range(injection.n_steps):
        residual = observer.update(
            injection.q[step], injection.qdot[step], injection.tau_meas[step], injection.dt
        )
    return residual


def test_residual_recovers_injected_torque_on_each_joint(model_terms: GmoModelTerms) -> None:
    """A step external torque on any joint is recovered by that joint's residual (①)."""
    for joint in range(7):
        residual = _run(model_terms, joint=joint, magnitude_nm=4.0)
        assert abs(residual[joint] - 4.0) < _TRACKING_TOL_NM


def test_residual_isolates_the_struck_joint(model_terms: GmoModelTerms) -> None:
    """The residual flags only the struck joint; every other joint stays quiet (①)."""
    for joint in range(7):
        residual = _run(model_terms, joint=joint, magnitude_nm=5.0)
        for other in range(7):
            if other != joint:
                assert abs(residual[other]) < _QUIET_JOINT_TOL_NM
        isolation = isolate_joints(residual, thresholds=[1.0] * 7)
        assert isolation.flagged == (joint,)
        assert isolation.dominant == joint
        assert isolation.is_contact


def test_no_injection_leaves_the_residual_at_zero(model_terms: GmoModelTerms) -> None:
    """With no external force the residual stays at zero — no phantom contact (①)."""
    observer = MomentumObserver(model_terms, gain=90.0)
    injection = inject_external_force(model_terms, joint=0, magnitude_nm=0.0, n_steps=400)
    observer.reset(injection.q[0], injection.qdot[0])
    residual = np.zeros(7)
    for step in range(injection.n_steps):
        residual = observer.update(
            injection.q[step], injection.qdot[step], injection.tau_meas[step], injection.dt
        )
    assert np.max(np.abs(residual)) < _QUIET_JOINT_TOL_NM
    assert not isolate_joints(residual, thresholds=[0.5] * 7).is_contact


def test_first_tick_residual_is_zero_without_reset(model_terms: GmoModelTerms) -> None:
    """The first `update` seeds `p(0)` itself, so the opening residual is exactly zero."""
    observer = MomentumObserver(model_terms, gain=120.0)
    injection = inject_external_force(model_terms, joint=2, magnitude_nm=3.0, n_steps=10)
    first = observer.update(injection.q[0], injection.qdot[0], injection.tau_meas[0], injection.dt)
    assert np.max(np.abs(first)) < _QUIET_JOINT_TOL_NM


def test_delayed_onset_is_recovered_after_it_starts(model_terms: GmoModelTerms) -> None:
    """A force that switches on mid-run is still recovered, with the residual quiet before onset."""
    observer = MomentumObserver(model_terms, gain=150.0)
    injection = inject_external_force(
        model_terms, joint=4, magnitude_nm=2.0, n_steps=500, start_step=200
    )
    observer.reset(injection.q[0], injection.qdot[0])
    before = np.zeros(7)
    residual = np.zeros(7)
    for step in range(injection.n_steps):
        residual = observer.update(
            injection.q[step], injection.qdot[step], injection.tau_meas[step], injection.dt
        )
        if step == 150:
            before = residual
    assert np.max(np.abs(before)) < _QUIET_JOINT_TOL_NM
    assert abs(residual[4] - 2.0) < _TRACKING_TOL_NM
