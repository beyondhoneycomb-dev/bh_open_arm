"""CG-4C-03a / CG-4C-03b — the Wilson interval reproduces the spec's cited figures.

`FR-SIM-056`: N=20, p̂=0.5 -> 95% CI ≈ ±21%p; N=50 -> ≈ ±13.6%p. Canonical Wilson
yields half-widths 0.2007 and 0.1336; the spec quotes those rounded to ±21/±13.6,
so the reproduction check allows the spec's rounding slack while an independent
recomputation of the Wilson formula pins the implementation to Wilson (not Wald).
"""

from __future__ import annotations

import math

from backend.eval.stats import Z_SCORE_95, wilson_interval

# The spec's cited half-widths (`FR-SIM-056`) and the slack their rounding needs:
# canonical Wilson is 0.2007 / 0.1336, so agreement to ~1.2%p covers the rounding.
SPEC_HALF_WIDTH_N20 = 0.21
SPEC_HALF_WIDTH_N50 = 0.136
SPEC_ROUNDING_TOLERANCE = 0.012

# The exact canonical Wilson bounds at p̂=0.5, which pin the formula (Wald would give
# [0.2809, 0.7191] at N=20 — the tight bound-check below would reject it).
EXACT_LOWER_N20 = 0.2993
EXACT_UPPER_N20 = 0.7007
EXACT_BOUND_TOLERANCE = 5e-4


def _wilson_half_width_reference(n_success: int, n_trials: int) -> float:
    """An independent restatement of the Wilson half-width, as a correctness oracle."""
    z = Z_SCORE_95
    n = float(n_trials)
    phat = n_success / n
    z2 = z * z
    denom = 1.0 + z2 / n
    return (z / denom) * math.sqrt(phat * (1.0 - phat) / n + z2 / (4.0 * n * n))


def test_wilson_n20_phat_half_reproduces_plus_minus_21() -> None:
    """CG-4C-03a: N=20, p̂=0.5 -> Wilson 95% CI ≈ ±21%p."""
    ci = wilson_interval(10, 20)
    assert abs(ci.half_width - SPEC_HALF_WIDTH_N20) < SPEC_ROUNDING_TOLERANCE
    # Pin it to canonical Wilson, not the wider Wald normal approximation.
    assert abs(ci.lower - EXACT_LOWER_N20) < EXACT_BOUND_TOLERANCE
    assert abs(ci.upper - EXACT_UPPER_N20) < EXACT_BOUND_TOLERANCE
    assert math.isclose(ci.half_width, _wilson_half_width_reference(10, 20), rel_tol=1e-12)


def test_wilson_n50_phat_half_reproduces_plus_minus_13_6() -> None:
    """CG-4C-03b: N=50, p̂=0.5 -> Wilson 95% CI ≈ ±13.6%p."""
    ci = wilson_interval(25, 50)
    assert abs(ci.half_width - SPEC_HALF_WIDTH_N50) < SPEC_ROUNDING_TOLERANCE
    assert math.isclose(ci.half_width, _wilson_half_width_reference(25, 50), rel_tol=1e-12)


def test_wilson_symmetric_and_centered_at_half() -> None:
    """At p̂=0.5 the Wilson interval is symmetric about 0.5 — a structural check."""
    ci = wilson_interval(10, 20)
    assert math.isclose((ci.lower + ci.upper) / 2.0, 0.5, abs_tol=1e-9)


def test_wider_ci_at_smaller_n() -> None:
    """Fewer trials must widen the interval — N=20 wider than N=50 at the same p̂."""
    assert wilson_interval(10, 20).half_width > wilson_interval(25, 50).half_width
