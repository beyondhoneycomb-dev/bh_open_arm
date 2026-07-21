"""Acceptance ③ — RTT distribution correctness with a histogram (summary-only banned).

Runs on fixture RTT samples. It pins the percentile arithmetic and, crucially,
that the histogram is present and its bin counts sum to the sample count — the
acceptance forbids a summary-only report.
"""

from __future__ import annotations

from ops.hw.usb.distribution import P50, P95, P99, compute_distribution, percentile


def test_percentiles_nearest_rank() -> None:
    """Nearest-rank percentiles pick actual samples, not interpolated values."""
    samples = list(range(1, 101))  # 1..100
    ordered = sorted(float(s) for s in samples)
    assert percentile(ordered, P50) == 50.0
    assert percentile(ordered, P95) == 95.0
    assert percentile(ordered, P99) == 99.0


def test_distribution_carries_histogram_summing_to_count() -> None:
    """The histogram is present and its counts total the sample count."""
    samples = [205.0, 212.4, 198.7, 231.9, 220.1, 209.3, 245.6, 201.2, 260.8, 215.0]
    dist = compute_distribution(samples, unit="us", bin_count=5)

    assert dist.count == len(samples)
    assert dist.histogram, "a distribution must carry a histogram, not just summary stats"
    assert sum(b.count for b in dist.histogram) == len(samples)
    assert dist.minimum == min(samples)
    assert dist.maximum == max(samples)


def test_as_dict_exposes_percentiles_and_bins() -> None:
    """The JSON projection carries both percentiles and the histogram bins."""
    dist = compute_distribution([200.0, 210.0, 260.0], unit="us")
    payload = dist.as_dict()

    assert set(payload["percentiles"]) == {"p50", "p95", "p99"}
    assert payload["histogram"], "histogram must be present in the artifact projection"
    assert payload["unit"] == "us"


def test_degenerate_range_still_has_a_bin() -> None:
    """All-equal samples collapse to one bin rather than a zero-width division."""
    dist = compute_distribution([210.0, 210.0, 210.0], unit="us")
    assert len(dist.histogram) == 1
    assert dist.histogram[0].count == 3


def test_empty_samples_are_honest_not_fabricated() -> None:
    """No samples yields count 0 and an empty histogram, not invented statistics."""
    dist = compute_distribution([], unit="us")
    assert dist.count == 0
    assert dist.histogram == ()
    assert dist.minimum is None and dist.maximum is None
