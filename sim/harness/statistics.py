"""Distribution comparison — is condition-4 ON statistically distinct from OFF?

Acceptance ③ is the anti-self-deception clause: the loaded and idle cycle-time
distributions must be *statistically distinguishable*, which proves the synthetic
load actually bites; the same test, run on a no-load profile, must find idle-vs-idle
NOT distinguishable, which proves the test is not rigged to pass anything.

The test is a two-sided Mann-Whitney U (a rank test, so it needs no normality
assumption and is robust to the fat GIL-stall tail) reduced to a p-value by the
normal approximation with tie and continuity correction, paired with Cliff's delta
as the effect size. Distinguishability requires *both* a small p-value and a
non-negligible effect: p-value alone would flag the tiny, inevitable drift between
two idle runs on a busy machine, so the effect-size floor is what keeps a no-load
comparison honestly non-distinguishable. Everything is analytic and deterministic —
no random permutation seed to make one run disagree with the next.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

# Defaults for the distinguishability verdict. A run is called distinguishable only
# when the rank test clears `alpha` AND the effect size clears `min_abs_effect`.
# 1e-3 mirrors the order of the overrun budget the gate cares about; the 0.30 Cliff's
# delta floor sits in the gap the interleaved measurement leaves open — a biting load
# lands near 0.6-0.8, residual drift between interleaved segments stays under ~0.15 —
# so below it two effectively-identical distributions are not called apart, which is
# what keeps the acceptance ③ anti-rig property (a no-load harness must not pass) from
# firing on machine noise.
DEFAULT_ALPHA = 1e-3
DEFAULT_MIN_ABS_EFFECT = 0.30


@dataclass(frozen=True)
class DistributionComparison:
    """The outcome of comparing two cycle-time distributions.

    Attributes:
        n_a: Sample count of the first group (the loaded condition, by convention).
        n_b: Sample count of the second group (the idle baseline, by convention).
        u_statistic: The Mann-Whitney U of group a against group b.
        z_score: Normal-approximation z of U, tie- and continuity-corrected.
        p_value: Two-sided p-value of the rank test.
        cliffs_delta: Effect size in [-1, 1]; positive means a tends to exceed b.
        median_shift_sec: median(a) - median(b), in seconds.
        alpha: The p-value threshold the verdict used.
        min_abs_effect: The Cliff's-delta magnitude floor the verdict used.
        distinguishable: True iff `p_value < alpha` and `|cliffs_delta| >= min_abs_effect`.
    """

    n_a: int
    n_b: int
    u_statistic: float
    z_score: float
    p_value: float
    cliffs_delta: float
    median_shift_sec: float
    alpha: float
    min_abs_effect: float
    distinguishable: bool

    def as_record(self) -> dict[str, Any]:
        """Serialize the comparison for the artifact.

        Returns:
            (dict[str, Any]) Every field, ready to embed under a condition result.
        """
        return {
            "n_a": self.n_a,
            "n_b": self.n_b,
            "u_statistic": self.u_statistic,
            "z_score": self.z_score,
            "p_value": self.p_value,
            "cliffs_delta": self.cliffs_delta,
            "median_shift_sec": self.median_shift_sec,
            "alpha": self.alpha,
            "min_abs_effect": self.min_abs_effect,
            "distinguishable": self.distinguishable,
        }


def _normal_sf(z: float) -> float:
    """Upper-tail probability of the standard normal at `z`.

    Args:
        z: A z-score.

    Returns:
        (float) P(Z > z), via `erfc`, so no statistics package is needed.
    """
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def _tie_correction_term(combined: np.ndarray) -> float:
    """Sum of `t**3 - t` over tie groups, used in the U variance correction.

    Args:
        combined: The pooled sample array of both groups.

    Returns:
        (float) The tie-correction sum; zero when there are no ties.
    """
    _, counts = np.unique(combined, return_counts=True)
    tied = counts[counts > 1].astype(np.float64)
    return float(np.sum(tied**3 - tied))


def compare_distributions(
    group_a: np.ndarray,
    group_b: np.ndarray,
    alpha: float = DEFAULT_ALPHA,
    min_abs_effect: float = DEFAULT_MIN_ABS_EFFECT,
) -> DistributionComparison:
    """Compare two cycle-time distributions with a Mann-Whitney U rank test.

    By convention group a is the loaded condition and group b the idle baseline, so a
    positive `cliffs_delta` and `median_shift_sec` mean the load inflated cycle time.

    Args:
        group_a: First distribution's samples (seconds).
        group_b: Second distribution's samples (seconds).
        alpha: p-value threshold for the distinguishability verdict.
        min_abs_effect: Cliff's-delta magnitude floor for the verdict.

    Returns:
        (DistributionComparison) The full test outcome and verdict. Degenerate inputs
        (an empty group, or two groups with zero rank variance) yield a
        non-distinguishable verdict with `p_value` 1.0 rather than an exception.
    """
    a = np.asarray(group_a, dtype=np.float64)
    b = np.asarray(group_b, dtype=np.float64)
    n_a = int(a.size)
    n_b = int(b.size)

    degenerate = DistributionComparison(
        n_a=n_a,
        n_b=n_b,
        u_statistic=0.0,
        z_score=0.0,
        p_value=1.0,
        cliffs_delta=0.0,
        median_shift_sec=(float(np.median(a)) - float(np.median(b))) if n_a and n_b else 0.0,
        alpha=alpha,
        min_abs_effect=min_abs_effect,
        distinguishable=False,
    )
    if n_a == 0 or n_b == 0:
        return degenerate

    combined = np.concatenate([a, b])
    ranks = _average_ranks(combined)
    rank_sum_a = float(np.sum(ranks[:n_a]))
    u_a = rank_sum_a - n_a * (n_a + 1) / 2.0

    product = n_a * n_b
    mean_u = product / 2.0
    total = n_a + n_b
    tie_term = _tie_correction_term(combined)
    variance = (product / 12.0) * ((total + 1) - tie_term / (total * (total - 1)))
    if variance <= 0.0:
        return degenerate

    sigma = math.sqrt(variance)
    continuity = 0.5
    z = (abs(u_a - mean_u) - continuity) / sigma
    z = max(z, 0.0)
    p_value = 2.0 * _normal_sf(z)
    p_value = min(1.0, p_value)

    cliffs_delta = 2.0 * u_a / product - 1.0
    median_shift = float(np.median(a)) - float(np.median(b))
    distinguishable = p_value < alpha and abs(cliffs_delta) >= min_abs_effect

    return DistributionComparison(
        n_a=n_a,
        n_b=n_b,
        u_statistic=u_a,
        z_score=z,
        p_value=p_value,
        cliffs_delta=cliffs_delta,
        median_shift_sec=median_shift,
        alpha=alpha,
        min_abs_effect=min_abs_effect,
        distinguishable=distinguishable,
    )


def _average_ranks(values: np.ndarray) -> np.ndarray:
    """Assign fractional ranks, averaging ties, in the original element order.

    Args:
        values: The pooled samples to rank.

    Returns:
        (np.ndarray) One rank per input element, 1-based, ties sharing their mean rank.
    """
    order = np.argsort(values, kind="mergesort")
    ordered = values[order]
    ranks_sorted = np.empty(values.size, dtype=np.float64)

    index = 0
    size = values.size
    while index < size:
        run_end = index + 1
        while run_end < size and ordered[run_end] == ordered[index]:
            run_end += 1
        average_rank = (index + 1 + run_end) / 2.0
        ranks_sorted[index:run_end] = average_rank
        index = run_end

    ranks = np.empty(values.size, dtype=np.float64)
    ranks[order] = ranks_sorted
    return ranks
