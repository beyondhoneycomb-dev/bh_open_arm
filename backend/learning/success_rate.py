"""Success-rate aggregation with Wilson and Clopper-Pearson intervals.

`14` FR-OPS-086 requires the real-hardware evaluation harness to report a success
rate as a point estimate plus a confidence interval, not a bare ratio: `8/10`
successes and `800/1000` successes are the same point estimate with very
different certainty, and a bare `0.8` hides that. Two intervals are provided
because they answer different questions — Wilson is the score interval used for
reporting, Clopper-Pearson is the exact (conservative) interval used when a lower
bound must be guaranteed to hold.

The interval mathematics is implemented here from `math` alone (no SciPy), so the
module carries no dependency beyond the standard library and the results are
reproducible: the regularized incomplete beta function via a Lentz continued
fraction, inverted by bisection for Clopper-Pearson, and the inverse normal CDF
via Acklam's rational approximation for the Wilson z-score.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

DEFAULT_CONFIDENCE = 0.95


@dataclass(frozen=True)
class ConfidenceInterval:
    """A two-sided confidence interval on a proportion.

    Attributes:
        lower: Lower bound, in [0, 1].
        upper: Upper bound, in [0, 1].
        confidence: The confidence level the bounds were computed at.
        method: The interval method, `wilson` or `clopper-pearson`.
    """

    lower: float
    upper: float
    confidence: float
    method: str


@dataclass(frozen=True)
class SuccessRate:
    """An aggregated success rate with its point estimate and both intervals.

    Attributes:
        successes: Number of successful trials.
        trials: Total number of trials.
        point_estimate: `successes / trials`.
        wilson: The Wilson score interval.
        clopper_pearson: The Clopper-Pearson exact interval.
    """

    successes: int
    trials: int
    point_estimate: float
    wilson: ConfidenceInterval
    clopper_pearson: ConfidenceInterval


def _validate_counts(successes: int, trials: int) -> None:
    """Reject counts that cannot describe a proportion.

    Args:
        successes: Number of successes.
        trials: Number of trials.

    Raises:
        ValueError: If `trials` is not positive or `successes` is out of range.
    """
    if trials <= 0:
        raise ValueError(f"trials must be positive; got {trials}")
    if not 0 <= successes <= trials:
        raise ValueError(f"successes must be in [0, {trials}]; got {successes}")


def _inverse_normal_cdf(probability: float) -> float:
    """Return the standard-normal quantile for a probability (Acklam, 2003).

    Accurate to roughly 1.15e-9 over the open interval, which is far tighter than
    any evaluation needs. Used only to turn a confidence level into the Wilson
    z-score, so `probability` is always well inside (0, 1).

    Args:
        probability: A probability in the open interval (0, 1).

    Returns:
        (float) The quantile z such that the standard-normal CDF at z equals the
        probability.

    Raises:
        ValueError: If `probability` is not strictly between 0 and 1.
    """
    if not 0.0 < probability < 1.0:
        raise ValueError(f"probability must be in (0, 1); got {probability}")

    a = (
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    )
    b = (
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    )
    c = (
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    )
    d = (
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    )
    low = 0.02425
    high = 1.0 - low

    if probability < low:
        q = math.sqrt(-2.0 * math.log(probability))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if probability <= high:
        q = probability - 0.5
        r = q * q
        return (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
            * q
            / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
        )
    q = math.sqrt(-2.0 * math.log(1.0 - probability))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
    )


def _beta_continued_fraction(x: float, a: float, b: float) -> float:
    """Evaluate the continued fraction for the incomplete beta (Lentz's method).

    Args:
        x: Argument in (0, 1).
        a: First shape parameter.
        b: Second shape parameter.

    Returns:
        (float) The continued-fraction value used by `_regularized_incomplete_beta`.
    """
    tiny = 1e-30
    max_iterations = 300
    tolerance = 1e-14

    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    result = d

    for iteration in range(1, max_iterations + 1):
        m = float(iteration)
        m2 = 2.0 * m
        numerator = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + numerator * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + numerator / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        result *= d * c
        numerator = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + numerator * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + numerator / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) < tolerance:
            break
    return result


def _regularized_incomplete_beta(x: float, a: float, b: float) -> float:
    """Return the regularized incomplete beta function I_x(a, b).

    Args:
        x: Argument in [0, 1].
        a: First shape parameter, positive.
        b: Second shape parameter, positive.

    Returns:
        (float) I_x(a, b) in [0, 1].
    """
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_beta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(log_beta + a * math.log(x) + b * math.log(1.0 - x))
    # The continued fraction converges fast only on the smaller tail; the beta
    # symmetry I_x(a,b) = 1 - I_(1-x)(b,a) moves the evaluation to that tail.
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_continued_fraction(x, a, b) / a
    return 1.0 - front * _beta_continued_fraction(1.0 - x, b, a) / b


def _inverse_regularized_incomplete_beta(target: float, a: float, b: float) -> float:
    """Invert I_x(a, b) = target for x by bisection.

    I_x is continuous and strictly increasing in x on (0, 1), so bisection
    converges monotonically without the failure modes a Newton step can hit near
    the boundary.

    Args:
        target: The probability to invert, in (0, 1).
        a: First shape parameter, positive.
        b: Second shape parameter, positive.

    Returns:
        (float) The x with I_x(a, b) == target, to full double precision.
    """
    low = 0.0
    high = 1.0
    for _ in range(200):
        mid = 0.5 * (low + high)
        if _regularized_incomplete_beta(mid, a, b) < target:
            low = mid
        else:
            high = mid
        if high - low < 1e-15:
            break
    return 0.5 * (low + high)


def wilson_interval(
    successes: int, trials: int, confidence: float = DEFAULT_CONFIDENCE
) -> ConfidenceInterval:
    """Compute the Wilson score interval for a proportion.

    Args:
        successes: Number of successes.
        trials: Number of trials, positive.
        confidence: Two-sided confidence level in (0, 1).

    Returns:
        (ConfidenceInterval) The Wilson score bounds, clamped to [0, 1].
    """
    _validate_counts(successes, trials)
    z = _inverse_normal_cdf(1.0 - (1.0 - confidence) / 2.0)
    n = float(trials)
    phat = successes / n
    denom = 1.0 + z * z / n
    center = (phat + z * z / (2.0 * n)) / denom
    margin = (z / denom) * math.sqrt(phat * (1.0 - phat) / n + z * z / (4.0 * n * n))
    return ConfidenceInterval(
        lower=max(0.0, center - margin),
        upper=min(1.0, center + margin),
        confidence=confidence,
        method="wilson",
    )


def clopper_pearson_interval(
    successes: int, trials: int, confidence: float = DEFAULT_CONFIDENCE
) -> ConfidenceInterval:
    """Compute the Clopper-Pearson exact interval for a proportion.

    The bounds are beta quantiles: the lower bound is the `alpha/2` quantile of
    `Beta(k, n-k+1)` and the upper bound the `1-alpha/2` quantile of
    `Beta(k+1, n-k)`, with the degenerate tails pinned to 0 (at `k=0`) and 1 (at
    `k=n`) where the beta parameter would be non-positive.

    Args:
        successes: Number of successes.
        trials: Number of trials, positive.
        confidence: Two-sided confidence level in (0, 1).

    Returns:
        (ConfidenceInterval) The Clopper-Pearson bounds in [0, 1].
    """
    _validate_counts(successes, trials)
    alpha = 1.0 - confidence
    k = successes
    n = trials

    lower = (
        0.0
        if k == 0
        else _inverse_regularized_incomplete_beta(alpha / 2.0, float(k), float(n - k + 1))
    )
    upper = (
        1.0
        if k == n
        else _inverse_regularized_incomplete_beta(1.0 - alpha / 2.0, float(k + 1), float(n - k))
    )
    return ConfidenceInterval(
        lower=lower,
        upper=upper,
        confidence=confidence,
        method="clopper-pearson",
    )


@dataclass
class SuccessRateAggregator:
    """Accumulate trial outcomes and render a success rate with both intervals.

    A single evaluation run reports one aggregate; this holds the running counts
    so a harness can push outcomes one at a time and read the interval at the end.

    Attributes:
        confidence: The confidence level both intervals are computed at.
    """

    confidence: float = DEFAULT_CONFIDENCE
    _successes: int = 0
    _trials: int = 0

    def record(self, success: bool) -> None:
        """Record one trial outcome.

        Args:
            success: True when the trial succeeded.
        """
        self._trials += 1
        if success:
            self._successes += 1

    def extend(self, outcomes: list[bool]) -> None:
        """Record a batch of trial outcomes.

        Args:
            outcomes: One boolean per trial.
        """
        for outcome in outcomes:
            self.record(outcome)

    def result(self) -> SuccessRate:
        """Render the aggregate success rate.

        Returns:
            (SuccessRate) Point estimate plus Wilson and Clopper-Pearson intervals.

        Raises:
            ValueError: If no trial has been recorded.
        """
        if self._trials == 0:
            raise ValueError("no trials recorded; success rate is undefined")
        return SuccessRate(
            successes=self._successes,
            trials=self._trials,
            point_estimate=self._successes / self._trials,
            wilson=wilson_interval(self._successes, self._trials, self.confidence),
            clopper_pearson=clopper_pearson_interval(
                self._successes, self._trials, self.confidence
            ),
        )
