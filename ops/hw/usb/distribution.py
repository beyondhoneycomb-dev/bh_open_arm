"""The RTT (and any latency) distribution computer for the M-1 harness.

`15` §2.10 M-1 and NFR-PRF-046 require RTT reported as `p50/p95/p99`, and the
`WP-0B-06` acceptance ③ is explicit that a summary-only figure is forbidden — the
artifact must carry the *distribution*, histogram included. This module is that
computer: it takes the raw per-cycle RTT samples and returns percentiles together
with a histogram, so a downstream reader can see the shape, not just three numbers.

Ownership and purity: this is pure arithmetic over a sample list. It opens no
socket, reads no hardware, and depends on nothing but the samples handed to it,
which is exactly why the `WP-0B-06` acceptance that runs on this host is the
distribution-computer correctness check — the samples may be synthetic fixtures or
real captures; the maths is identical.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# The three percentile levels every latency NFR in `15` §2.10 reports at.
P50 = 50.0
P95 = 95.0
P99 = 99.0
REPORTED_PERCENTILES = (P50, P95, P99)

# Default histogram resolution. A distribution reported without bins is a summary,
# which acceptance ③ forbids, so the histogram is never optional; this only sets
# how finely a non-degenerate range is sliced.
DEFAULT_BIN_COUNT = 20


@dataclass(frozen=True)
class HistogramBin:
    """One half-open histogram bin `[lower, upper)`, except the last is closed.

    Attributes:
        lower: Inclusive lower edge, in the sample unit.
        upper: Exclusive upper edge (inclusive for the final bin).
        count: Number of samples that fell in the bin.
    """

    lower: float
    upper: float
    count: int


@dataclass(frozen=True)
class Distribution:
    """A latency distribution: percentiles plus the histogram behind them.

    The histogram is a first-class field, not a rendering afterthought: acceptance
    ③ rejects a summary-only report, so a `Distribution` with an empty histogram is
    only ever the empty-sample case.

    Attributes:
        unit: Sample unit, e.g. "us" for microseconds.
        count: Number of samples.
        minimum: Smallest sample, or None when there are no samples.
        maximum: Largest sample, or None when there are no samples.
        percentiles: Percentile level -> value, for `REPORTED_PERCENTILES`.
        histogram: The bins, in ascending order; empty only when count is 0.
    """

    unit: str
    count: int
    minimum: float | None
    maximum: float | None
    percentiles: dict[float, float]
    histogram: tuple[HistogramBin, ...]

    def as_dict(self) -> dict[str, object]:
        """Project to a JSON-serialisable mapping for the artifact.

        Returns:
            (dict[str, object]) The distribution as plain data, histogram included.
        """
        return {
            "unit": self.unit,
            "count": self.count,
            "min": self.minimum,
            "max": self.maximum,
            "percentiles": {f"p{int(level)}": value for level, value in self.percentiles.items()},
            "histogram": [
                {"lower": b.lower, "upper": b.upper, "count": b.count} for b in self.histogram
            ],
        }


def percentile(sorted_samples: list[float], level: float) -> float:
    """Return the nearest-rank percentile of an already-sorted sample list.

    Nearest-rank (rather than interpolation) is chosen because RTT is reported to
    inform a hard budget, and the nearest-rank p99 is a value that actually
    occurred rather than one synthesised between two observations.

    Args:
        sorted_samples: Samples in ascending order; must be non-empty.
        level: Percentile level in the open interval (0, 100].

    Returns:
        (float) The sample at the nearest rank for `level`.

    Raises:
        ValueError: If `sorted_samples` is empty.
    """
    if not sorted_samples:
        raise ValueError("percentile of an empty sample list is undefined")
    rank = math.ceil(level / 100.0 * len(sorted_samples))
    index = min(max(rank, 1), len(sorted_samples)) - 1
    return sorted_samples[index]


def _build_histogram(sorted_samples: list[float], bin_count: int) -> tuple[HistogramBin, ...]:
    """Bin sorted samples into `bin_count` equal-width bins over `[min, max]`.

    A degenerate range (every sample equal) collapses to a single unit-less bin so
    the histogram is still present rather than a zero-width division.

    Args:
        sorted_samples: Samples in ascending order; must be non-empty.
        bin_count: Number of bins for a non-degenerate range.

    Returns:
        (tuple[HistogramBin, ...]) Bins in ascending order.
    """
    low = sorted_samples[0]
    high = sorted_samples[-1]
    if high <= low:
        return (HistogramBin(lower=low, upper=high, count=len(sorted_samples)),)

    width = (high - low) / bin_count
    counts = [0] * bin_count
    for sample in sorted_samples:
        slot = int((sample - low) / width)
        # The maximum sample lands exactly on the top edge; fold it into the last bin.
        counts[min(slot, bin_count - 1)] += 1
    return tuple(
        HistogramBin(
            lower=low + width * index, upper=low + width * (index + 1), count=counts[index]
        )
        for index in range(bin_count)
    )


def compute_distribution(
    samples: list[float],
    unit: str,
    bin_count: int = DEFAULT_BIN_COUNT,
) -> Distribution:
    """Compute percentiles and a histogram from raw latency samples.

    Args:
        samples: Raw samples in any order; may be empty.
        unit: Sample unit recorded on the result, e.g. "us".
        bin_count: Histogram resolution for a non-degenerate range.

    Returns:
        (Distribution) Percentiles and histogram. On empty input every statistic is
        None/empty and the count is 0 — an honest empty rather than a fabricated one.
    """
    if not samples:
        return Distribution(
            unit=unit,
            count=0,
            minimum=None,
            maximum=None,
            percentiles=dict.fromkeys(REPORTED_PERCENTILES, 0.0),
            histogram=(),
        )
    ordered = sorted(samples)
    return Distribution(
        unit=unit,
        count=len(ordered),
        minimum=ordered[0],
        maximum=ordered[-1],
        percentiles={level: percentile(ordered, level) for level in REPORTED_PERCENTILES},
        histogram=_build_histogram(ordered, bin_count),
    )
