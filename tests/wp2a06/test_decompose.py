"""Acceptance ①: the four-stage path decomposition runs on synthetic boundary timestamps.

The machinery is what runs here; the numbers are synthetic. These check that a sample
splits into the four `02b` stages correctly, that the split telescopes back to the total,
that out-of-order timestamps are refused rather than yielding a negative segment, and that
each segment and the total are recorded as full distributions (`03` §5.7 forbids
summary-only), never a bare percentile.
"""

from __future__ import annotations

import pytest

from backend.stopbench import (
    SEGMENT_ORDER,
    NonMonotonicSampleError,
    StopPathDecomposition,
    StopPathSample,
    StopPathSegment,
)
from tests.wp2a06.conftest import make_sample


def test_segment_order_is_the_four_named_stages() -> None:
    assert SEGMENT_ORDER == (
        StopPathSegment.HARNESS_EVENT,
        StopPathSegment.TRANSMIT,
        StopPathSegment.SCHEDULER,
        StopPathSegment.CAN,
    )


def test_segment_durations_are_the_consecutive_differences() -> None:
    sample = make_sample(1.0, 0.002, 0.001, 0.003, 0.004)
    durations = sample.segment_durations()
    assert durations[StopPathSegment.HARNESS_EVENT] == pytest.approx(0.002)
    assert durations[StopPathSegment.TRANSMIT] == pytest.approx(0.001)
    assert durations[StopPathSegment.SCHEDULER] == pytest.approx(0.003)
    assert durations[StopPathSegment.CAN] == pytest.approx(0.004)


def test_segments_telescope_to_the_total() -> None:
    sample = make_sample(2.5, 0.002, 0.001, 0.003, 0.004)
    assert sample.total() == pytest.approx(0.010)
    assert sample.reconciles()


@pytest.mark.parametrize(
    "boundaries",
    [
        (0.0, 0.001, 0.0005, 0.002, 0.003),  # transmit before harness end
        (0.0, 0.001, 0.002, 0.0015, 0.003),  # can_write before scheduler
        (0.0, 0.001, 0.002, 0.003, 0.0025),  # first byte before write
    ],
)
def test_non_monotonic_sample_is_refused(boundaries: tuple[float, ...]) -> None:
    with pytest.raises(NonMonotonicSampleError):
        StopPathSample(*boundaries)


def test_decomposition_per_segment_distribution_reflects_the_input() -> None:
    samples = [make_sample(index * 0.001, 0.002, 0.001, 0.003, 0.004) for index in range(20)]
    decomposition = StopPathDecomposition(samples)
    assert decomposition.sample_count == 20
    # Every sample has the same per-segment split, so each segment's p50 is that constant.
    assert decomposition.segment(StopPathSegment.HARNESS_EVENT).summary()["p50"] == pytest.approx(
        0.002
    )
    assert decomposition.segment(StopPathSegment.CAN).summary()["p50"] == pytest.approx(0.004)
    assert decomposition.total().summary()["p50"] == pytest.approx(0.010)


def test_decomposition_records_full_distributions_not_summary_only() -> None:
    samples = [make_sample(index * 0.001, 0.002, 0.001, 0.003, 0.004) for index in range(8)]
    record = StopPathDecomposition(samples).as_record()
    assert set(record["segments"]) == {segment.value for segment in SEGMENT_ORDER}
    for segment_record in record["segments"].values():
        # Raw samples and the binned histogram are both present — the whole distribution,
        # not a percentile triple.
        assert segment_record["raw_samples"]
        assert "histogram" in segment_record
    assert record["total"]["raw_samples"]


def test_empty_decomposition_is_empty_not_fabricated() -> None:
    record = StopPathDecomposition([]).as_record()
    assert record["sample_count"] == 0
    assert record["total"]["raw_samples"] == []
    for segment_record in record["segments"].values():
        assert segment_record["raw_samples"] == []
