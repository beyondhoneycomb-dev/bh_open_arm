"""Acceptance 1: the three-stage decomposition runs on synthetic boundary timestamps.

The machinery is what runs here; the numbers are synthetic. These check that a sample splits
into the three reaction-path stages correctly, that the split telescopes back to the total,
that out-of-order timestamps are refused rather than yielding a negative segment, and that
each segment and the total are recorded as full distributions (never a bare percentile),
which is the histogram WP-2C-06 acceptance 1 requires be produced and recorded.
"""

from __future__ import annotations

import pytest

from backend.reaction_bench import (
    SEGMENT_ORDER,
    NonMonotonicSampleError,
    ReactionSample,
    ReactionSegment,
    ReactionTimeDecomposition,
)
from tests.wp2c06.conftest import make_sample


def test_segment_order_is_the_three_named_stages() -> None:
    assert SEGMENT_ORDER == (
        ReactionSegment.SELECT,
        ReactionSegment.SCHEDULE,
        ReactionSegment.CAN,
    )


def test_segment_durations_are_the_consecutive_differences() -> None:
    sample = make_sample(1.0, 0.002, 0.003, 0.004)
    durations = sample.segment_durations()
    assert durations[ReactionSegment.SELECT] == pytest.approx(0.002)
    assert durations[ReactionSegment.SCHEDULE] == pytest.approx(0.003)
    assert durations[ReactionSegment.CAN] == pytest.approx(0.004)


def test_segments_telescope_to_the_total() -> None:
    sample = make_sample(2.5, 0.002, 0.003, 0.004)
    assert sample.total() == pytest.approx(0.009)
    assert sample.reconciles()


@pytest.mark.parametrize(
    "boundaries",
    [
        (0.001, 0.0005, 0.002, 0.003),  # reaction selected before confirm
        (0.0, 0.002, 0.0015, 0.003),  # scheduler write before select
        (0.0, 0.002, 0.003, 0.0025),  # first byte before write
    ],
)
def test_non_monotonic_sample_is_refused(boundaries: tuple[float, ...]) -> None:
    with pytest.raises(NonMonotonicSampleError):
        ReactionSample(*boundaries)


def test_decomposition_per_segment_distribution_reflects_the_input() -> None:
    samples = [make_sample(index * 0.001, 0.002, 0.003, 0.004) for index in range(20)]
    decomposition = ReactionTimeDecomposition(samples)
    assert decomposition.sample_count == 20
    # Every sample has the same per-segment split, so each segment's p50 is that constant.
    assert decomposition.segment(ReactionSegment.SELECT).summary()["p50"] == pytest.approx(0.002)
    assert decomposition.segment(ReactionSegment.CAN).summary()["p50"] == pytest.approx(0.004)
    assert decomposition.total().summary()["p50"] == pytest.approx(0.009)


def test_decomposition_records_full_distributions_not_summary_only() -> None:
    samples = [make_sample(index * 0.001, 0.002, 0.003, 0.004) for index in range(8)]
    record = ReactionTimeDecomposition(samples).as_record()
    assert set(record["segments"]) == {segment.value for segment in SEGMENT_ORDER}
    for segment_record in record["segments"].values():
        # Raw samples and the binned histogram are both present — the whole distribution,
        # not a percentile triple.
        assert segment_record["raw_samples"]
        assert "histogram" in segment_record
    assert record["total"]["raw_samples"]


def test_empty_decomposition_is_empty_not_fabricated() -> None:
    record = ReactionTimeDecomposition([]).as_record()
    assert record["sample_count"] == 0
    assert record["total"]["raw_samples"] == []
    for segment_record in record["segments"].values():
        assert segment_record["raw_samples"] == []
