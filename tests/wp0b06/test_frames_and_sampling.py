"""Acceptance ⑤ — frames-consumed-per-cycle (PG-CAN-001) + tool-output parsing.

Runs on a fixture `motor_sampling_check` log plus direct frame-count lists. It pins
the `PG-CAN-001` classification (32 = pattern B normal, 16 = pattern A or window
error) and that the sweep parser extracts the RTT samples and per-cycle frame
counts the distribution and frames recorders consume.
"""

from __future__ import annotations

from pathlib import Path

from ops.hw.usb.frames import FrameVerdict, record_frames_per_cycle
from ops.hw.usb.sampling import parse_run

_FIXTURES = Path(__file__).parent / "fixtures"


def test_thirty_two_frames_is_pattern_b_normal() -> None:
    """A steady 32 frames/cycle classifies as pattern B normal."""
    record = record_frames_per_cycle([32, 32, 32, 32])
    assert record.mode == 32
    assert record.verdict is FrameVerdict.PATTERN_B_NORMAL
    assert record.as_dict()["pg_can_001_input"] == 32


def test_sixteen_frames_flags_pattern_a_or_window_error() -> None:
    """A steady 16 frames/cycle is the PG-CAN-001 investigate case."""
    record = record_frames_per_cycle([16, 16, 16])
    assert record.mode == 16
    assert record.verdict is FrameVerdict.PATTERN_A_OR_WINDOW_ERROR


def test_mode_not_mean_drives_the_verdict() -> None:
    """The dominant count, not an average, is the classification input."""
    record = record_frames_per_cycle([32, 32, 32, 16])
    assert record.mode == 32
    assert record.verdict is FrameVerdict.PATTERN_B_NORMAL


def test_unexpected_count_is_neither_pattern() -> None:
    """A count that is neither 16 nor 32 is flagged unexpected, not silently accepted."""
    record = record_frames_per_cycle([8, 8, 8])
    assert record.verdict is FrameVerdict.UNEXPECTED


def test_parse_run_extracts_rtt_and_frames() -> None:
    """The sweep-log parser yields per-cycle RTT samples, frames, and the actual Hz."""
    text = (_FIXTURES / "msc_can0_500.log").read_text(encoding="utf-8")
    run = parse_run(text)

    assert run.target_hz == 500
    assert run.actual_hz == 499.0  # the SUMMARY line's value wins over per-cycle
    assert len(run.rtt_us) == 15
    assert run.rtt_us[0] == 205.0
    assert all(frames == 32 for frames in run.frames_per_cycle)


def test_parse_run_feeds_frames_recorder() -> None:
    """Parsed frame counts flow into the PG-CAN-001 recorder as pattern B."""
    text = (_FIXTURES / "msc_can0_500.log").read_text(encoding="utf-8")
    run = parse_run(text)
    record = record_frames_per_cycle(run.frames_per_cycle)
    assert record.verdict is FrameVerdict.PATTERN_B_NORMAL
