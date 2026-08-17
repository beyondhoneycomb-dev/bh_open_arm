"""Frames the device itself skipped, read out of the gaps in its own timestamps.

`06` §2.6c asks for device frame-number continuity so a gap is surfaced independently of the raw
count. Nothing on this rig can supply it: `CAP_PROP_POS_FRAMES` reads `-1.0` on a live V4L2
capture, so `missing_frame_numbers` is empty for every real run and the count is all there is.

The count alone is not enough, and a ten-minute run over three cameras is what showed why. All
three recorded exactly 17718 frames against 18001 expected — the same number from three
independent cameras, because the runner polls slots in one fixed-order pass and every slot
therefore advances at the slowest one's rate. The count-based figure is the loop's throughput
with the cameras' losses folded into it.

The devices disagreed with each other in their own timestamps: 163, 168 and 204 intervals longer
than a frame. That is the per-camera signal the frame numbers would have carried, and it is
already in `capture_ts.json`.
"""

from __future__ import annotations

import pytest

from backend.camera.droprate import skipped_frames_from_timestamps

TARGET_FPS = 30.0
INTERVAL_NS = 33_400_000


def _stream(intervals: list[int]) -> list[int]:
    """Build a timestamp sequence from a list of inter-frame intervals in nanoseconds."""
    stamps = [0]
    for interval in intervals:
        stamps.append(stamps[-1] + interval)
    return stamps


def test_an_unbroken_stream_skipped_nothing() -> None:
    """The negative first, so a skip count is not something every stream produces."""
    stamps = _stream([INTERVAL_NS] * 20)

    assert skipped_frames_from_timestamps(stamps, TARGET_FPS) == 0


def test_a_doubled_interval_is_one_skipped_frame() -> None:
    """Measured on this rig: a 66.8 ms gap between two 33.4 ms frames is one frame the device
    never delivered."""
    stamps = _stream([INTERVAL_NS, INTERVAL_NS * 2, INTERVAL_NS])

    assert skipped_frames_from_timestamps(stamps, TARGET_FPS) == 1


def test_a_longer_gap_counts_every_frame_inside_it() -> None:
    """The worst interval in the ten-minute run was 233 ms — six frames, not one."""
    stamps = _stream([INTERVAL_NS, INTERVAL_NS * 7, INTERVAL_NS])

    assert skipped_frames_from_timestamps(stamps, TARGET_FPS) == 6


def test_jitter_short_of_a_frame_is_not_a_skip() -> None:
    """Intervals ran 33.24-33.51 ms on a healthy stream; rounding must absorb that."""
    stamps = _stream([33_240_000, 33_510_000, 33_300_000, 33_490_000])

    assert skipped_frames_from_timestamps(stamps, TARGET_FPS) == 0


def test_a_stream_too_short_to_have_an_interval_reports_nothing() -> None:
    """One frame has no gap, and zero frames is a slot that never answered — not a skip."""
    assert skipped_frames_from_timestamps([], TARGET_FPS) == 0
    assert skipped_frames_from_timestamps([0], TARGET_FPS) == 0


def test_a_rate_at_or_below_zero_is_refused() -> None:
    """Without a rate there is no interval to divide by, and every gap would be infinite."""
    with pytest.raises(ValueError, match="must be positive"):
        skipped_frames_from_timestamps(_stream([INTERVAL_NS]), 0.0)
