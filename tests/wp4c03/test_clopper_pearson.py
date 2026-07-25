"""CG-4C-03d — Clopper-Pearson is added on the boundary and its bound widens Wilson.

`02c` §3.3: when `n_success ∈ {0, n_trials}` the report carries Clopper-Pearson
alongside Wilson, and the boundary bound is at least as extreme as Wilson's (the
whole point — Wilson understates the boundary). Off the boundary Clopper-Pearson is
absent. The closed-form boundary interval is cross-checked against SciPy's general
Beta quantile so the widening is real Clopper-Pearson, not a fabricated number.
"""

from __future__ import annotations

import math

from scipy import stats

from backend.eval.stats import (
    IntervalError,
    clopper_pearson_boundary_interval,
    is_boundary,
    wilson_interval,
)
from tests.wp4c03.support import report

_HALF_ALPHA = 0.025


def _beta_oracle_bounds(n_success: int, n_trials: int) -> tuple[float, float]:
    """Independent Clopper-Pearson bounds via the general Beta quantile (oracle)."""
    lower = (
        0.0
        if n_success == 0
        else float(stats.beta.ppf(_HALF_ALPHA, n_success, n_trials - n_success + 1))
    )
    upper = (
        1.0
        if n_success == n_trials
        else float(stats.beta.ppf(1 - _HALF_ALPHA, n_success + 1, n_trials - n_success))
    )
    return lower, upper


def test_all_failures_adds_clopper_pearson_upper_ge_wilson() -> None:
    """CG-4C-03d: n_success=0 -> CP present, CP upper >= Wilson upper, CP lower = 0."""
    rep = report(n_success=0, n_trials=20)
    assert rep.ci_clopper_pearson_95 is not None
    assert rep.ci_clopper_pearson_95.upper >= rep.ci_wilson_95.upper
    assert rep.ci_clopper_pearson_95.lower == 0.0


def test_all_successes_adds_clopper_pearson_lower_le_wilson() -> None:
    """The symmetric boundary: n_success=n_trials -> CP lower <= Wilson lower, CP upper = 1."""
    rep = report(n_success=20, n_trials=20)
    assert rep.ci_clopper_pearson_95 is not None
    assert rep.ci_clopper_pearson_95.lower <= rep.ci_wilson_95.lower
    assert rep.ci_clopper_pearson_95.upper == 1.0


def test_interior_has_no_clopper_pearson() -> None:
    """Off the boundary the report carries Wilson alone (no permanent extra width)."""
    assert report(n_success=10, n_trials=20).ci_clopper_pearson_95 is None
    assert is_boundary(10, 20) is False


def test_boundary_closed_form_matches_beta_oracle() -> None:
    """The closed-form boundary interval equals the general Beta-quantile interval."""
    for n_success, n_trials in ((0, 20), (0, 50), (20, 20), (50, 50)):
        ci = clopper_pearson_boundary_interval(n_success, n_trials)
        lower, upper = _beta_oracle_bounds(n_success, n_trials)
        assert math.isclose(ci.lower, lower, abs_tol=1e-9)
        assert math.isclose(ci.upper, upper, abs_tol=1e-9)


def test_interior_request_is_refused() -> None:
    """Clopper-Pearson is boundary-only by contract; an interior request raises."""
    try:
        clopper_pearson_boundary_interval(10, 20)
    except IntervalError:
        return
    raise AssertionError("interior Clopper-Pearson request should raise IntervalError")


def test_clopper_pearson_widens_wilson_at_the_protocol_n() -> None:
    """At the protocol N (=20) CP widens Wilson on both boundaries — the stated 대가.

    This is the regime CG-4C-03d and the ±21%p reproduction live in (N=20). CP's
    extreme bound is more extreme than Wilson's: upper is higher at k=0, lower is
    lower at k=n, and the interval is wider both times.
    """
    all_fail_cp = clopper_pearson_boundary_interval(0, 20)
    all_fail_wilson = wilson_interval(0, 20)
    assert all_fail_cp.upper >= all_fail_wilson.upper
    assert (all_fail_cp.upper - all_fail_cp.lower) >= (
        all_fail_wilson.upper - all_fail_wilson.lower
    )

    all_pass_cp = clopper_pearson_boundary_interval(20, 20)
    all_pass_wilson = wilson_interval(20, 20)
    assert all_pass_cp.lower <= all_pass_wilson.lower
    assert (all_pass_cp.upper - all_pass_cp.lower) >= (
        all_pass_wilson.upper - all_pass_wilson.lower
    )


def test_boundary_widening_is_a_small_n_property_not_universal() -> None:
    """Honest bound on the claim: CP's boundary correction is a small-N need.

    The Wilson upper at k=0 is `z²/(n+z²)` and CP's is `1-(α/2)^(1/n)`; since
    `z²=3.841 > -ln(0.025)=3.689`, Wilson's boundary upper overtakes CP's for large
    n (crossover ~n=45). So "CP is always wider" holds where the protocol operates
    (N≈20) but not universally — this asserts the crossover exists rather than
    faking a green by pretending CP dominates at every N.
    """
    small_n_cp = clopper_pearson_boundary_interval(0, 20)
    small_n_wilson = wilson_interval(0, 20)
    assert small_n_cp.upper > small_n_wilson.upper

    large_n_cp = clopper_pearson_boundary_interval(0, 50)
    large_n_wilson = wilson_interval(0, 50)
    assert large_n_wilson.upper > large_n_cp.upper
