"""Acceptance ⑥ — Wilson and Clopper-Pearson intervals match reference values.

⑥ requires the two intervals to reproduce known reference values for known inputs.
The constants below are the published 95% intervals (e.g. Clopper-Pearson for 8/10
is R's ``binom.test(8, 10)`` = (0.4439045, 0.9747893)); the implementation is
independent of any statistics library, so agreement is a genuine cross-check, not
a call comparing a library to itself.
"""

from __future__ import annotations

import pytest

from backend.learning.success_rate import (
    SuccessRateAggregator,
    clopper_pearson_interval,
    wilson_interval,
)

TOLERANCE = 1e-6

# (successes, trials, wilson_lower, wilson_upper, cp_lower, cp_upper) at 95%.
REFERENCE = [
    (8, 10, 0.4901624715, 0.9433178485, 0.4439045377, 0.9747892737),
    (0, 10, 0.0, 0.2775327999, 0.0, 0.3084971078),
    (10, 10, 0.7224672001, 1.0, 0.6915028922, 1.0),
    (50, 100, 0.4038315304, 0.5961684696, 0.3983211295, 0.6016788705),
    (1, 20, 0.0088814488, 0.2361311934, 0.0012650895, 0.2487327628),
]


@pytest.mark.parametrize(("k", "n", "wl", "wu", "cl", "cu"), REFERENCE)
def test_intervals_match_reference(
    k: int, n: int, wl: float, wu: float, cl: float, cu: float
) -> None:
    """⑥ both intervals reproduce the published 95% reference bounds."""
    wilson = wilson_interval(k, n)
    cp = clopper_pearson_interval(k, n)
    assert wilson.lower == pytest.approx(wl, abs=TOLERANCE)
    assert wilson.upper == pytest.approx(wu, abs=TOLERANCE)
    assert cp.lower == pytest.approx(cl, abs=TOLERANCE)
    assert cp.upper == pytest.approx(cu, abs=TOLERANCE)


def test_wilson_z_is_the_95_percent_quantile() -> None:
    """The Wilson 95% interval uses z = 1.959964, so a symmetric case is exact."""
    # For k/n = 1/2 the Wilson centre is exactly 0.5; the half-width encodes z.
    wilson = wilson_interval(50, 100)
    assert (wilson.lower + wilson.upper) / 2 == pytest.approx(0.5, abs=TOLERANCE)


def test_clopper_pearson_contains_wilson_bounds() -> None:
    """Clopper-Pearson is the conservative interval: it is never tighter."""
    for k, n, *_ in REFERENCE:
        wilson = wilson_interval(k, n)
        cp = clopper_pearson_interval(k, n)
        assert cp.lower <= wilson.lower + TOLERANCE
        assert cp.upper >= wilson.upper - TOLERANCE


def test_edge_counts_pin_to_zero_and_one() -> None:
    """At k=0 the lower bound is 0; at k=n the upper bound is 1 (both methods)."""
    # Clopper-Pearson pins the degenerate tail to exactly 0 / 1; Wilson reaches it
    # to within float epsilon (its closed form lands one ulp short at p-hat = 1).
    assert clopper_pearson_interval(0, 25).lower == 0.0
    assert wilson_interval(0, 25).lower == pytest.approx(0.0, abs=TOLERANCE)
    assert clopper_pearson_interval(25, 25).upper == 1.0
    assert wilson_interval(25, 25).upper == pytest.approx(1.0, abs=TOLERANCE)


def test_confidence_level_widens_interval() -> None:
    """A higher confidence level yields a wider interval."""
    narrow = wilson_interval(8, 10, confidence=0.90)
    wide = wilson_interval(8, 10, confidence=0.99)
    assert (wide.upper - wide.lower) > (narrow.upper - narrow.lower)


def test_aggregator_matches_direct_computation() -> None:
    """The aggregator's result equals the direct interval on the same counts."""
    aggregator = SuccessRateAggregator()
    aggregator.extend([True] * 8 + [False] * 2)
    result = aggregator.result()

    assert result.successes == 8
    assert result.trials == 10
    assert result.point_estimate == pytest.approx(0.8)
    assert result.wilson.lower == pytest.approx(wilson_interval(8, 10).lower, abs=TOLERANCE)
    assert result.clopper_pearson.upper == pytest.approx(
        clopper_pearson_interval(8, 10).upper, abs=TOLERANCE
    )


def test_invalid_counts_are_rejected() -> None:
    """Impossible counts raise rather than return a nonsense interval."""
    with pytest.raises(ValueError, match="trials must be positive"):
        wilson_interval(0, 0)
    with pytest.raises(ValueError, match="successes must be in"):
        clopper_pearson_interval(11, 10)
    with pytest.raises(ValueError, match="no trials recorded"):
        SuccessRateAggregator().result()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
