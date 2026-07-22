"""Acceptance ① (separation): the fit residual is separated from gravity, Coriolis and inertia.

Two controls, because a separation statistic is only worth reporting if it can fail. The
positive control is the correct basis: every joint's residual is uncorrelated with the model
signals and the fit explains almost all the friction variance. The negative control is exactly
the §2.0 failure — the v1-convention shoulder (the +pi/2 joint2 shift omitted), which feeds a
wrong gravity to the fit. There the friction fit silently absorbs the gravity error, the
post-fit residual still tracks the gravity signal, and the statistic reports `separated=False`.
That the statistic bites on the documented failure is what makes its pass on the correct basis
mean something.
"""

from __future__ import annotations

import math

import numpy as np

from backend.friction import (
    FrictionParams,
    IdentificationResult,
    InverseDynamicsBasis,
    SyntheticLog,
    fit_joint,
    identify_friction,
    separation_stats,
)
from backend.friction.seed import V1_SEED_FRICTION
from backend.gravity import Arm, MuJoCoV2GravityBackend

_SHOULDER_JOINT = 1  # joint2, zero-based: the joint the +pi/2 convention error corrupts most.


def test_correct_basis_separates_every_joint(result: IdentificationResult) -> None:
    stats = separation_stats(result)
    assert len(stats) == 7
    for stat in stats:
        assert stat.separated
        assert stat.max_abs_corr() < 0.2
        assert stat.r2 > 0.95


def _contaminated_result(
    synthetic: SyntheticLog, result: IdentificationResult
) -> IdentificationResult:
    """Re-fit against a residual built with the v1-convention (unshifted joint2) gravity.

    The measured torque and the true components are unchanged; only the gravity subtracted
    during identification is wrong, by exactly the +pi/2 joint2 shift §2.0 forbids omitting.
    """
    log = synthetic.log
    components = result.components
    backend = MuJoCoV2GravityBackend(Arm.RIGHT)
    wrong_gravity = np.zeros_like(components.gravity)
    for sample in range(log.n_samples):
        pose = log.q[sample].copy()
        pose[_SHOULDER_JOINT] -= math.pi / 2.0
        wrong_gravity[sample] = backend.tau_grav(pose)
    wrong_total = components.total - components.gravity + wrong_gravity
    contaminated_residual = log.tau - wrong_total
    fits = tuple(
        fit_joint(joint, log.qd[:, joint], contaminated_residual[:, joint], V1_SEED_FRICTION[joint])
        for joint in range(7)
    )
    return IdentificationResult(
        fits=fits,
        components=components,
        friction_residual=contaminated_residual,
        velocity=log.qd,
    )


def test_wrong_gravity_fails_separation(
    synthetic: SyntheticLog, result: IdentificationResult
) -> None:
    contaminated = _contaminated_result(synthetic, result)
    stats = separation_stats(contaminated)
    # The shoulder gravity error is the largest, so its residual correlation is unmistakable and
    # its separation verdict must be False.
    shoulder = stats[_SHOULDER_JOINT]
    assert not shoulder.separated
    assert abs(shoulder.corr_gravity) > 0.4
    # No joint may quietly pass while a gravity error of this size is in the residual.
    assert not any(stat.separated for stat in stats)


def test_wrong_gravity_biases_the_friction_offset(
    synthetic: SyntheticLog, result: IdentificationResult
) -> None:
    contaminated = _contaminated_result(synthetic, result)
    # The absorbed gravity shows up as a grossly wrong offset — the friction fit has eaten the
    # model error, which is the silent corruption §2.0 describes.
    shoulder_offset = contaminated.fits[_SHOULDER_JOINT].params.f_o
    truth_offset = synthetic.truth[_SHOULDER_JOINT].f_o
    assert abs(shoulder_offset - truth_offset) > 1.0


def test_basis_does_not_depend_on_the_friction_result(
    basis: InverseDynamicsBasis, synthetic: SyntheticLog, result: IdentificationResult
) -> None:
    # Self-approval guard: the derivation basis (the subtracted rigid-body dynamics and the
    # friction residual) must be a function of the trajectory alone, never of the fit result.
    # Identifying with a very different seed must leave the residual and components identical.
    scrambled_seed = tuple(FrictionParams(f_o=0.0, f_v=1.0, f_c=5.0, k_eff=1.0) for _ in range(7))
    other = identify_friction(synthetic.log, basis, scrambled_seed)
    assert np.allclose(other.friction_residual, result.friction_residual)
    assert np.allclose(other.components.total, result.components.total)
