"""The rank test separates a shifted distribution and leaves an unshifted one alone.

This is the instrument behind acceptance ③: distinguishability must fire on a real
shift and stay silent on statistical noise, and it must need both a small p-value and
a non-negligible effect size so a large-n but tiny-shift comparison is not called
apart. These are pure synthetic-array checks — no timing — so they pin the test's
logic independently of the harness.
"""

from __future__ import annotations

import numpy as np
import pytest

from sim.harness.statistics import DEFAULT_MIN_ABS_EFFECT, compare_distributions


def test_identical_distributions_not_distinguishable() -> None:
    """Two samples from the same distribution are not called apart."""
    rng = np.random.default_rng(0)
    a = rng.normal(5.0e-3, 1.0e-4, size=800)
    b = rng.normal(5.0e-3, 1.0e-4, size=800)
    result = compare_distributions(a, b)
    assert not result.distinguishable
    assert abs(result.cliffs_delta) < DEFAULT_MIN_ABS_EFFECT


def test_clearly_shifted_distribution_distinguishable() -> None:
    """A distribution shifted well above the noise is distinguishable, with positive delta."""
    rng = np.random.default_rng(1)
    idle = rng.normal(5.0e-3, 1.0e-4, size=800)
    loaded = idle + 3.0e-4  # a clean, consistent shift up
    result = compare_distributions(loaded, idle)
    assert result.distinguishable
    assert result.cliffs_delta > DEFAULT_MIN_ABS_EFFECT
    assert result.median_shift_sec > 0.0
    assert result.p_value < result.alpha


def test_tiny_shift_below_effect_floor_not_distinguishable() -> None:
    """A shift too small to matter is not distinguishable even at large n and small p."""
    rng = np.random.default_rng(2)
    idle = rng.normal(5.0e-3, 1.0e-4, size=6000)
    loaded = idle + 5.0e-6  # a shift far below one standard deviation
    result = compare_distributions(loaded, idle)
    assert abs(result.cliffs_delta) < DEFAULT_MIN_ABS_EFFECT
    assert not result.distinguishable


def test_same_median_different_spread_not_distinguishable() -> None:
    """A symmetric spread change with the same median does not fool the rank test.

    This is why the victim loop uses a relative period: a self-correcting loop would
    only widen the spread under load, and a spread-only difference must not read as a
    shift.
    """
    rng = np.random.default_rng(3)
    tight = rng.normal(5.0e-3, 5.0e-5, size=1500)
    wide = rng.normal(5.0e-3, 3.0e-4, size=1500)
    result = compare_distributions(wide, tight)
    assert abs(result.cliffs_delta) < DEFAULT_MIN_ABS_EFFECT
    assert not result.distinguishable


def test_empty_group_is_degenerate_not_distinguishable() -> None:
    """An empty group yields a non-distinguishable verdict, not an exception."""
    result = compare_distributions(np.array([]), np.array([1.0, 2.0, 3.0]))
    assert not result.distinguishable
    assert result.p_value == 1.0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
