"""Binomial confidence intervals: Wilson (canonical) and Clopper-Pearson (boundary).

`02c` §3.3 fixes the division of labour between the two, and it is load-bearing:

- **Wilson is canonical.** `FR-SIM-056`, `NFR-PRF-050`, `FR-OPS-086` and
  `FR-SIM-153` all name Wilson; the plan reports the Wilson 95% interval for
  every success rate, and its arithmetic reproduces the spec's cited numbers
  (N=20, p̂=0.5 -> ≈±21%p; N=50 -> ≈±13.6%p).
- **Clopper-Pearson only on the boundary.** The Wilson interval collapses one
  side when p̂ hits 0 or 1 — a 20-trial shutout (p̂=0) is common in early
  evaluation and its Wilson upper bound understates the true uncertainty. So the
  plan adds the exact (conservative) Clopper-Pearson interval, but ONLY when
  `n_success ∈ {0, n_trials}`. Off the boundary the plan reports Wilson alone;
  Clopper-Pearson's permanent extra width would otherwise inflate the "no
  improvement shown" verdict and raise the Type-II error of checkpoint
  comparison (`02c` §3.3 대가).

At the two boundaries the Clopper-Pearson interval has a closed form — the Beta
inverse-CDF degenerates because one shape parameter is 1 — so this module needs
no SciPy: `k=0 -> [0, 1-(α/2)^(1/n)]` and `k=n -> [(α/2)^(1/n), 1]`. That is the
exact Clopper-Pearson interval, not an approximation of it, and the tests
cross-check it against the general Beta quantile to prove so.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from backend.eval.stats.constants import (
    HALF_ALPHA,
    METHOD_CLOPPER_PEARSON,
    METHOD_WILSON,
    Z_SCORE_95,
)


class IntervalError(ValueError):
    """Raised when an interval is asked for on input it is not defined for.

    Two cases: a non-positive trial count (no proportion exists), and a
    Clopper-Pearson request for an interior `n_success` (this package computes
    Clopper-Pearson only on the boundary, by contract — `02c` §3.3).
    """


@dataclass(frozen=True)
class ConfidenceInterval:
    """A closed proportion interval `[lower, upper]` with the method that made it.

    Frozen because an interval is a computed fact about a fixed (k, n): editing a
    bound in place would decouple it from the data it summarises. Bounds are
    always within `[0, 1]` — a proportion interval cannot leave the unit line, and
    the constructors clamp float underflow at the boundary to keep that true.

    Attributes:
        lower: The lower bound, in `[0, 1]`.
        upper: The upper bound, in `[0, 1]`, never below `lower`.
        method: Which interval this is (`METHOD_WILSON` / `METHOD_CLOPPER_PEARSON`).
    """

    lower: float
    upper: float
    method: str

    @property
    def half_width(self) -> float:
        """Half the interval's width — the ±%p figure the spec quotes.

        At p̂=0.5 the Wilson interval is symmetric, so this is the "±" the spec
        cites for the reproduction check (CG-4C-03a/b). Off-centre it is still a
        well-defined half-width, but the interval is no longer symmetric about the
        point estimate, so read it as `(upper - lower) / 2`, not as a ± offset.

        Returns:
            (float) `(upper - lower) / 2`.
        """
        return (self.upper - self.lower) / 2.0

    def contains(self, proportion: float) -> bool:
        """Whether a proportion lies within the closed interval."""
        return self.lower <= proportion <= self.upper

    def overlaps(self, other: ConfidenceInterval) -> bool:
        """Whether two intervals share any point.

        The overlap test that drives "우열 미판정": two checkpoints whose Wilson
        intervals touch are not distinguishable by this evidence, so ranking them
        would be ranking noise (`02c` §3.3 / CG-4C-06d).

        Args:
            other: The interval to test against.

        Returns:
            (bool) True when the closed intervals intersect.
        """
        return self.lower <= other.upper and other.lower <= self.upper


def _clamp_unit(value: float) -> float:
    """Clamp a float to `[0, 1]`, absorbing boundary underflow.

    The Wilson lower bound at k=0 is analytically exactly 0, but the subtraction
    can land at a tiny negative float; a proportion bound must not read as
    negative, so it is clamped rather than reported as `-1e-17`.
    """
    return min(1.0, max(0.0, value))


def wilson_interval(n_success: int, n_trials: int) -> ConfidenceInterval:
    """The Wilson score 95% interval — the canonical CI for every success rate.

    This is the interval `02c` §3.3 reports always. Its arithmetic is the textbook
    Wilson score formula with `z = Φ⁻¹(0.975)`, and it reproduces the spec's cited
    figures: N=20, p̂=0.5 -> half-width ≈ 0.20 (spec ≈±21%p); N=50 -> ≈ 0.134
    (spec ≈±13.6%p). The small gap to the spec's rounded ±21/±13.6 is the spec's
    rounding, not a different formula — the tests assert both the exact value and
    the spec-figure agreement.

    Args:
        n_success: Number of successful trials, `0 <= n_success <= n_trials`.
        n_trials: Number of trials, strictly positive.

    Returns:
        (ConfidenceInterval) The Wilson 95% interval, bounds in `[0, 1]`.

    Raises:
        IntervalError: When `n_trials <= 0` or `n_success` is out of range.
    """
    _validate_counts(n_success, n_trials)
    z = Z_SCORE_95
    n = float(n_trials)
    phat = n_success / n
    z_squared = z * z
    denominator = 1.0 + z_squared / n
    centre = (phat + z_squared / (2.0 * n)) / denominator
    margin = (z / denominator) * math.sqrt(phat * (1.0 - phat) / n + z_squared / (4.0 * n * n))
    return ConfidenceInterval(
        lower=_clamp_unit(centre - margin),
        upper=_clamp_unit(centre + margin),
        method=METHOD_WILSON,
    )


def is_boundary(n_success: int, n_trials: int) -> bool:
    """Whether `n_success` sits on a boundary (all failures or all successes).

    The boundary is the only place `02c` §3.3 adds Clopper-Pearson, because it is
    the only place the Wilson interval collapses one side.

    Args:
        n_success: Number of successful trials.
        n_trials: Number of trials.

    Returns:
        (bool) True when `n_success` is 0 or equal to `n_trials`.
    """
    return n_success == 0 or n_success == n_trials


def clopper_pearson_boundary_interval(n_success: int, n_trials: int) -> ConfidenceInterval:
    """The exact Clopper-Pearson 95% interval, defined here only on the boundary.

    Reporting Clopper-Pearson off the boundary is refused, not silently computed:
    `02c` §3.3 buys its conservative extra width deliberately and only for the
    p̂∈{0,1} case, so an interior request is a contract violation to surface, not a
    number to hand back. On the boundary one Beta shape parameter is 1 and the
    inverse-CDF is elementary:

        k = 0      -> [0, 1 - (α/2)^(1/n)]
        k = n      -> [(α/2)^(1/n), 1]

    This is the exact Clopper-Pearson interval at those points (the tests confirm
    it equals the general Beta-quantile form), so no SciPy dependency is incurred.

    Args:
        n_success: Number of successful trials; must be `0` or `n_trials`.
        n_trials: Number of trials, strictly positive.

    Returns:
        (ConfidenceInterval) The Clopper-Pearson 95% interval on the boundary.

    Raises:
        IntervalError: When `n_trials <= 0`, counts are out of range, or
            `n_success` is interior (not on the boundary).
    """
    _validate_counts(n_success, n_trials)
    if not is_boundary(n_success, n_trials):
        raise IntervalError(
            f"Clopper-Pearson is reported only on the boundary (n_success in {{0, n_trials}}); "
            f"got n_success={n_success}, n_trials={n_trials}. Off the boundary the canonical "
            "interval is Wilson (02c §3.3)."
        )
    tail = HALF_ALPHA ** (1.0 / float(n_trials))
    if n_success == 0:
        return ConfidenceInterval(
            lower=0.0, upper=_clamp_unit(1.0 - tail), method=METHOD_CLOPPER_PEARSON
        )
    return ConfidenceInterval(lower=_clamp_unit(tail), upper=1.0, method=METHOD_CLOPPER_PEARSON)


def _validate_counts(n_success: int, n_trials: int) -> None:
    """Reject inputs no binomial proportion is defined for."""
    if n_trials <= 0:
        raise IntervalError(f"n_trials must be positive to form a proportion, got {n_trials}")
    if not 0 <= n_success <= n_trials:
        raise IntervalError(
            f"n_success must satisfy 0 <= n_success <= n_trials; got n_success={n_success}, "
            f"n_trials={n_trials}"
        )
