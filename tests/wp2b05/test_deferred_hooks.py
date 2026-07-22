"""Deferred rig hooks — they refuse to pass without evidence, and hold the logic (②③④⑤⑦).

Each hook is the on-rig re-verification of an item that needs a real CAN bus. Called without
the rig evidence, it raises `HardwareDeferredError` — a deferral is never a silent green.
Called with evidence, it runs the real check, including the FAIL_BLOCKING branches.
"""

from __future__ import annotations

import pytest

from backend.friction_log.errors import HardwareDeferredError, LoggerTransmitError
from backend.friction_log.reverify import (
    reverify_frame_count_per_cycle,
    reverify_logging_frequency,
    reverify_logging_not_exceeding_tick,
    reverify_single_writer,
    reverify_ticks_not_interrupted,
)


def test_all_hooks_defer_without_rig_evidence() -> None:
    """② ③ ④ ⑤ ⑦ each raise HardwareDeferredError when their rig evidence is absent."""
    with pytest.raises(HardwareDeferredError):
        reverify_single_writer(None)
    with pytest.raises(HardwareDeferredError):
        reverify_ticks_not_interrupted(None)
    with pytest.raises(HardwareDeferredError):
        reverify_logging_frequency(None, None, None)
    with pytest.raises(HardwareDeferredError):
        reverify_logging_not_exceeding_tick(None, None)
    with pytest.raises(HardwareDeferredError):
        reverify_frame_count_per_cycle(None)


def test_single_writer_accepts_one_and_rejects_two() -> None:
    """② One bus sender passes; a second sender is the FAIL_BLOCKING two-writer case."""
    assert reverify_single_writer(("scheduler", "scheduler")) == "scheduler"
    with pytest.raises(LoggerTransmitError):
        reverify_single_writer(("scheduler", "logger"))


def test_missed_ticks_is_fail_blocking() -> None:
    """③ Zero missed ticks passes; any missed tick is a dropped-arm path."""
    reverify_ticks_not_interrupted(0)
    with pytest.raises(LoggerTransmitError):
        reverify_ticks_not_interrupted(2)


def test_logging_frequency_bounds() -> None:
    """④ A frequency at or below both bounds passes; above either fails."""
    assert reverify_logging_frequency(900.0, 1000.0, 950.0) is True
    assert reverify_logging_frequency(1100.0, 1000.0, 950.0) is False
    assert reverify_logging_frequency(970.0, 1000.0, 950.0) is False


def test_logging_not_exceeding_tick_is_fail_blocking() -> None:
    """⑤ Frames at or below the bus tick count pass; more frames means it drove the bus."""
    reverify_logging_not_exceeding_tick(1000, 1000)
    with pytest.raises(LoggerTransmitError):
        reverify_logging_not_exceeding_tick(1001, 1000)


def test_frame_count_holds_the_tick_condition_at_sixteen() -> None:
    """⑦ 16 frames per cycle holds the pattern-A tick condition; 32 forces the variant."""
    assert reverify_frame_count_per_cycle(16) is True
    assert reverify_frame_count_per_cycle(32) is False
