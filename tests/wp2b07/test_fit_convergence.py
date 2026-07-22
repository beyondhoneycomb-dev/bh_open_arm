"""Acceptance ① (convergence): every joint's fit converges and recovers the injected friction.

The synthetic log carries friction at known parameters. A correct fit converges and returns
those parameters within the measurement noise; this is the "per-joint fit converges" half of
acceptance ①, demonstrated on a signal whose truth is known so recovery is checkable.
"""

from __future__ import annotations

from backend.friction import IdentificationResult, SyntheticLog

# Tolerances the recovered parameters must meet against the injected truth. The Coulomb and
# viscous terms carry the friction and are recovered tightly; the tanh slope is looser because
# it is identified only from the low-velocity knee samples, and the offset is an absolute Nm
# tolerance because it is small enough that a relative bound would be dominated by noise.
_FC_REL_TOL = 0.08
_FV_REL_TOL = 0.15
_K_EFF_REL_TOL = 0.15
_FO_ABS_TOL = 0.03


def test_every_joint_converged(result: IdentificationResult) -> None:
    assert all(fit.converged for fit in result.fits)
    assert len(result.fits) == 7


def test_recovers_injected_coulomb_and_slope(
    result: IdentificationResult, synthetic: SyntheticLog
) -> None:
    for fit, truth in zip(result.fits, synthetic.truth, strict=True):
        got = fit.params
        assert abs(got.f_c - truth.f_c) <= _FC_REL_TOL * truth.f_c
        assert abs(got.k_eff - truth.k_eff) <= _K_EFF_REL_TOL * truth.k_eff


def test_recovers_injected_viscous_and_offset(
    result: IdentificationResult, synthetic: SyntheticLog
) -> None:
    for fit, truth in zip(result.fits, synthetic.truth, strict=True):
        got = fit.params
        assert abs(got.f_v - truth.f_v) <= _FV_REL_TOL * truth.f_v
        assert abs(got.f_o - truth.f_o) <= _FO_ABS_TOL


def test_fit_residual_is_near_the_noise_floor(result: IdentificationResult) -> None:
    # The synthetic noise is 0.02 Nm; a converged fit leaves a residual of that order, not the
    # much larger friction signal it was supposed to explain.
    for fit in result.fits:
        assert fit.residual_rms_nm < 0.05
