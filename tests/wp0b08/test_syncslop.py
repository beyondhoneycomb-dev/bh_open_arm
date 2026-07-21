"""Acceptance ⑤ — the sync-slop distribution computer, histogram required.

Two properties are checked: the nearest-match distribution has the known answer for a
constant-offset fixture, and the histogram is *present* — `02a` WP-0B-08 ⑤ forbids a
summary alone, and the type makes a histogram-less report unconstructable.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.camera import fixtures
from backend.camera.constants import NANOSECONDS_PER_MILLISECOND
from backend.camera.syncslop import (
    SyncSlopReport,
    build_slop_reports,
    nearest_match_diffs_ns,
)

_FIVE_MS_NS = 5 * NANOSECONDS_PER_MILLISECOND


def test_constant_offset_gives_that_offset_everywhere() -> None:
    """A stream trailing by a constant 5 ms yields a 5 ms difference on every match."""
    streams = fixtures.capture_ts_pair(slop_ns=_FIVE_MS_NS, frame_count=100)
    diffs = nearest_match_diffs_ns(streams["a"], streams["b"])
    assert all(d == _FIVE_MS_NS for d in diffs)


def test_report_summary_matches_the_known_offset() -> None:
    """The q50/q99/max of a constant-5 ms fixture are all 5 ms."""
    streams = fixtures.capture_ts_pair(slop_ns=_FIVE_MS_NS, frame_count=100)
    report = build_slop_reports(streams)[0]
    assert report.pair == ("a", "b")
    assert report.q50_ms == pytest.approx(5.0)
    assert report.q99_ms == pytest.approx(5.0)
    assert report.max_ms == pytest.approx(5.0)
    assert report.stddev_ms == pytest.approx(0.0)


def test_histogram_is_present_and_totals_the_samples() -> None:
    """The histogram is attached and its bin counts sum to the sample count (⑤)."""
    streams = fixtures.capture_ts_pair(slop_ns=_FIVE_MS_NS, frame_count=100)
    report = build_slop_reports(streams)[0]
    assert report.histogram, "a slop report must attach a histogram, not summary only"
    assert sum(b.count for b in report.histogram) == report.sample_count == 100
    populated = [b for b in report.histogram if b.count]
    assert len(populated) == 1
    assert populated[0].lo_ms <= 5.0 < populated[0].hi_ms


def test_report_cannot_be_built_without_a_histogram() -> None:
    """`SyncSlopReport.histogram` has no default — a summary-only report is a TypeError."""
    fields = {f.name for f in dataclasses.fields(SyncSlopReport)}
    assert "histogram" in fields
    with pytest.raises(TypeError):
        SyncSlopReport(  # type: ignore[call-arg]
            pair=("a", "b"),
            sample_count=1,
            q50_ms=0.0,
            q99_ms=0.0,
            max_ms=0.0,
            stddev_ms=0.0,
        )


def test_varied_offsets_spread_across_bins() -> None:
    """A drifting offset produces a multi-bin histogram, not a single spike."""
    base = [i * NANOSECONDS_PER_MILLISECOND * 33 for i in range(60)]
    drift = [t + i * NANOSECONDS_PER_MILLISECOND for i, t in enumerate(base)]
    report = build_slop_reports({"a": base, "b": drift})[0]
    populated = [b for b in report.histogram if b.count]
    assert len(populated) >= 2
    assert report.max_ms > report.q50_ms


def test_empty_stream_is_rejected() -> None:
    """A pair needs both sides — an empty slot is an error, not a silent zero."""
    with pytest.raises(ValueError, match="at least one timestamp"):
        nearest_match_diffs_ns([1, 2, 3], [])
