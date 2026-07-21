"""Per-slot-pair capture_ts difference distribution — the sync-slop computer.

`06` §2.6 / FR-CAM-015 / FR-CAM-022 want the timestamp difference between every slot
pair as a *distribution*, and `02a` WP-0B-08 ⑤ is explicit: a summary alone is
forbidden, the histogram must be attached. That constraint is encoded in the type —
`SyncSlopReport.histogram` has no default, so a report cannot be constructed without
its histogram, and no code path can emit summary statistics on their own.

Pairing is nearest-match on capture_ts (the `ApproximateTime` model, §2.6b): for each
timestamp in one slot, the closest timestamp in the other. A dropped frame therefore
shifts nothing — matching is by time, not by index. capture_ts is nanoseconds
(FR-CAM-014); the report speaks milliseconds.
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from backend.camera.constants import (
    DEFAULT_SLOP_BIN_WIDTH_MS,
    NANOSECONDS_PER_MILLISECOND,
)


def nearest_match_diffs_ns(reference: Sequence[int], other: Sequence[int]) -> list[int]:
    """Return, for each reference timestamp, the absolute gap to its nearest neighbour.

    Args:
        reference: Sorted-or-unsorted capture_ts (ns) of the reference slot.
        other: Capture_ts (ns) of the other slot.

    Returns:
        (list[int]) One absolute nanosecond difference per reference timestamp.

    Raises:
        ValueError: If either sequence is empty — a pair needs both sides to match.
    """
    if not reference or not other:
        raise ValueError("both slots need at least one timestamp to form a pair")
    ordered = sorted(other)
    diffs: list[int] = []
    for stamp in reference:
        position = bisect.bisect_left(ordered, stamp)
        candidates = []
        if position < len(ordered):
            candidates.append(abs(ordered[position] - stamp))
        if position > 0:
            candidates.append(abs(stamp - ordered[position - 1]))
        diffs.append(min(candidates))
    return diffs


@dataclass(frozen=True)
class HistogramBin:
    """One closed-open bin `[lo_ms, hi_ms)` of a slop histogram.

    Attributes:
        lo_ms: Inclusive lower edge in milliseconds.
        hi_ms: Exclusive upper edge in milliseconds.
        count: Samples that fell in the bin.
    """

    lo_ms: float
    hi_ms: float
    count: int


def _quantile_ms(sorted_ms: Sequence[float], q: float) -> float:
    """Linear-interpolation quantile over an already-sorted millisecond sequence."""
    if not sorted_ms:
        return 0.0
    if len(sorted_ms) == 1:
        return sorted_ms[0]
    position = q * (len(sorted_ms) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return sorted_ms[low]
    fraction = position - low
    return sorted_ms[low] * (1 - fraction) + sorted_ms[high] * fraction


def _build_histogram(values_ms: Sequence[float], bin_width_ms: float) -> tuple[HistogramBin, ...]:
    """Bin millisecond differences into fixed-width closed-open bins.

    Args:
        values_ms: Difference samples in milliseconds.
        bin_width_ms: Width of each bin.

    Returns:
        (tuple[HistogramBin, ...]) Bins covering zero up to the maximum sample.
    """
    if bin_width_ms <= 0:
        raise ValueError(f"bin width must be positive, got {bin_width_ms}")
    if not values_ms:
        return ()
    top = max(values_ms)
    bin_count = int(top // bin_width_ms) + 1
    counts = [0] * bin_count
    for value in values_ms:
        index = min(int(value // bin_width_ms), bin_count - 1)
        counts[index] += 1
    return tuple(
        HistogramBin(lo_ms=i * bin_width_ms, hi_ms=(i + 1) * bin_width_ms, count=counts[i])
        for i in range(bin_count)
    )


@dataclass(frozen=True)
class SyncSlopReport:
    """The distribution of one slot pair's capture_ts differences.

    The histogram is a required field, not an optional add-on: `02a` WP-0B-08 ⑤ bans
    emitting summary statistics without the full distribution, and a type with no
    default for `histogram` makes that ban unrepresentable.

    Attributes:
        pair: The two slot keys, sorted.
        sample_count: Number of matched differences.
        q50_ms: Median difference.
        q99_ms: 99th-percentile difference (the NFR-CAM-002 acceptance quantile).
        max_ms: Largest difference.
        stddev_ms: Population standard deviation (drift indicator, FR-CAM-022).
        histogram: The full binned distribution.
    """

    pair: tuple[str, str]
    sample_count: int
    q50_ms: float
    q99_ms: float
    max_ms: float
    stddev_ms: float
    histogram: tuple[HistogramBin, ...]

    @classmethod
    def from_diffs_ns(
        cls,
        pair: tuple[str, str],
        diffs_ns: Sequence[int],
        bin_width_ms: float = DEFAULT_SLOP_BIN_WIDTH_MS,
    ) -> SyncSlopReport:
        """Build a report from raw nanosecond differences.

        Args:
            pair: The two slot keys.
            diffs_ns: Absolute capture_ts differences in nanoseconds.
            bin_width_ms: Histogram bin width in milliseconds.

        Returns:
            (SyncSlopReport) Summary plus the required histogram.

        Raises:
            ValueError: If `diffs_ns` is empty.
        """
        if not diffs_ns:
            raise ValueError(f"pair {pair} has no matched differences to summarise")
        values_ms = sorted(d / NANOSECONDS_PER_MILLISECOND for d in diffs_ns)
        mean = sum(values_ms) / len(values_ms)
        variance = sum((v - mean) ** 2 for v in values_ms) / len(values_ms)
        return cls(
            pair=(min(pair), max(pair)),
            sample_count=len(values_ms),
            q50_ms=_quantile_ms(values_ms, 0.50),
            q99_ms=_quantile_ms(values_ms, 0.99),
            max_ms=values_ms[-1],
            stddev_ms=math.sqrt(variance),
            histogram=_build_histogram(values_ms, bin_width_ms),
        )


def build_slop_reports(
    streams: Mapping[str, Sequence[int]],
    bin_width_ms: float = DEFAULT_SLOP_BIN_WIDTH_MS,
) -> list[SyncSlopReport]:
    """Build a slop report for every unordered slot pair.

    Args:
        streams: Slot key to its capture_ts (ns) sequence. At least two slots.
        bin_width_ms: Histogram bin width in milliseconds.

    Returns:
        (list[SyncSlopReport]) One report per pair, sorted by pair.

    Raises:
        ValueError: If fewer than two slots are supplied.
    """
    slots = sorted(streams)
    if len(slots) < 2:
        raise ValueError("a slop distribution needs at least two slots")
    reports: list[SyncSlopReport] = []
    for i, left in enumerate(slots):
        for right in slots[i + 1 :]:
            diffs = nearest_match_diffs_ns(streams[left], streams[right])
            reports.append(SyncSlopReport.from_diffs_ns((left, right), diffs, bin_width_ms))
    return reports
