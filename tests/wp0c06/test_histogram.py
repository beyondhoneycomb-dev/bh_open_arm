"""The histogram keeps the whole distribution, not just a summary (acceptance ⑥).

The artifact refusal for summary-only publication (⑥) depends on the histogram
actually carrying raw samples and complete bins. This suite pins those, plus the
overrun-rate tolerance behaviour that lets the sweep's `time.sleep` floor not count
as an overrun.
"""

from __future__ import annotations

import numpy as np
import pytest

from sim.harness.histogram import CycleTimeHistogram


def test_record_carries_raw_samples_and_full_histogram() -> None:
    """The record has every raw sample and a bin for every sample."""
    samples = np.linspace(4.0e-3, 6.0e-3, 500)
    histogram = CycleTimeHistogram(samples)
    record = histogram.as_record()
    assert record["sample_count"] == 500
    assert len(record["raw_samples"]) == 500
    assert sum(record["histogram"]["counts"]) == 500
    assert "summary" in record  # the convenience summary is present too, not instead


def test_samples_are_immutable() -> None:
    """A published histogram's samples cannot be mutated after construction."""
    histogram = CycleTimeHistogram(np.array([1.0, 2.0, 3.0]))
    with pytest.raises(ValueError, match="read-only|assignment destination"):
        histogram.samples[0] = 99.0


def test_overrun_tolerance_excludes_the_sleep_floor() -> None:
    """A small tolerance band keeps cycles just above the period from counting as overruns."""
    period = 4.0e-3
    just_over = np.full(1000, period * 1.02)  # 2% over — inside a 5% band
    histogram = CycleTimeHistogram(just_over)
    assert histogram.overrun_rate(period, tolerance=0.0) == 1.0
    assert histogram.overrun_rate(period, tolerance=0.05) == 0.0


def test_overrun_counts_real_overruns() -> None:
    """Cycles well past the tolerance band count as overruns."""
    period = 4.0e-3
    samples = np.concatenate([np.full(900, period), np.full(100, period * 1.5)])
    histogram = CycleTimeHistogram(samples)
    assert histogram.overrun_rate(period, tolerance=0.05) == pytest.approx(0.1)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
