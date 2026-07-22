"""WP-3A-02 ④ — the LeRobot `timestamp` is a synthetic grid, marked so in meta.

`02b` §5.2 WP-3A-02 ④ requires the dataset `timestamp` column — `frame_index / fps`
— to be presented as a synthetic playback grid, not a capture instant. These tests
fix that the grid value is typed as CTR-PRIM's `SyntheticGridTimestamp` (a distinct
domain from `CaptureTimestamp`), and that the meta record the recorder writes and
the UI shows flags it synthetic. The capture instant itself stays CLOCK_MONOTONIC
nanoseconds, consumed from the primitive.
"""

from __future__ import annotations

import pytest

import contracts.capture as cap
from contracts.prim import CaptureTimestamp, SyntheticGridTimestamp, TimestampDomain


def test_lerobot_timestamp_is_the_frame_index_over_fps_grid() -> None:
    """The dataset timestamp is `frame_index / fps`, in the synthetic-grid domain."""
    grid = cap.synthetic_grid_timestamp(frame_index=30, fps=15.0)
    assert isinstance(grid, SyntheticGridTimestamp)
    assert grid.seconds == pytest.approx(2.0)
    assert grid.domain == TimestampDomain.SYNTHETIC_GRID


def test_synthetic_grid_and_capture_instant_are_distinct_domains() -> None:
    """A synthetic grid coordinate and a real capture instant are not the same type."""
    grid = cap.synthetic_grid_timestamp(frame_index=1, fps=10.0)
    capture = cap.CaptureTimestamp(mono_ns=123_456)
    assert isinstance(grid, SyntheticGridTimestamp)
    assert isinstance(capture, CaptureTimestamp)
    assert grid.domain != capture.domain
    assert type(grid) is not type(capture)


def test_meta_flags_the_timestamp_as_synthetic() -> None:
    """The meta record the recorder/UI reads marks the dataset timestamp synthetic."""
    meta = cap.lerobot_timestamp_meta()
    assert meta["is_synthetic"] is True
    assert meta["timestamp_domain"] == TimestampDomain.SYNTHETIC_GRID.value
    assert "synthetic" in meta["note"]
    assert "capture" in meta["note"]


def test_capture_instant_is_monotonic_nanoseconds() -> None:
    """The capture instant is CLOCK_MONOTONIC nanoseconds, consumed from CTR-PRIM."""
    assert cap.CLOCK_SOURCE == "CLOCK_MONOTONIC"
    assert cap.TIMESTAMP_UNIT_NS == "ns"
    assert cap.CaptureTimestamp(mono_ns=1).domain == TimestampDomain.CAPTURE


def test_non_positive_fps_is_refused() -> None:
    """The synthetic grid cannot be placed without a positive frame rate."""
    with pytest.raises(cap.CaptureContractError):
        cap.synthetic_grid_timestamp(frame_index=1, fps=0.0)


def test_capture_match_miss_is_a_counted_drop_not_a_defect() -> None:
    """A capture-to-frame match miss is a counted drop, consumed from CTR-PRIM's queue."""
    assert cap.capture_match_drop_classification() == cap.DropClassification.COUNTED
    assert cap.CAPTURE_MATCH_QUEUE.drop_classification == cap.DropClassification.COUNTED
