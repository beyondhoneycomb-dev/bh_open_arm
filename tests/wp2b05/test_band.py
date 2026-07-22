"""Achieved-band analysis — frequency/jitter runs here, but stays provisional (④⑤).

The stats are computed from the frame timestamps, so they run without hardware. The band
they feed is marked provisional whenever the real tick rate and `f_max_python` are absent,
which they are on this host, so a synthetic capture is never mistaken for a final figure.
"""

from __future__ import annotations

import pytest

from backend.friction_log.band import (
    PATTERN_SCHEDULER_TAP,
    achieved_band,
    logging_did_not_outrun_ticks,
    logging_stats,
)
from backend.friction_log.frame import LogFrame


def _frame_at(index: int, at: float) -> LogFrame:
    """A minimal frame at a given timestamp; only `at` matters to the stats."""
    return LogFrame(index=index, at=at, positions=(), velocities=(), torques=())


def test_stats_measure_frequency_over_uniform_intervals() -> None:
    """A 1 ms cadence reads as 1000 Hz with zero jitter."""
    frames = tuple(_frame_at(index, index * 0.001) for index in range(11))
    stats = logging_stats(frames)
    assert stats.frame_count == 11
    assert stats.achieved_hz == pytest.approx(1000.0)
    assert stats.jitter_sec == pytest.approx(0.0, abs=1e-9)
    assert stats.max_interval_sec == pytest.approx(0.001)


def test_stats_report_jitter_on_uneven_intervals() -> None:
    """An uneven cadence shows a non-zero jitter and the widest gap."""
    frames = (
        _frame_at(0, 0.000),
        _frame_at(1, 0.001),
        _frame_at(2, 0.004),
    )
    stats = logging_stats(frames)
    assert stats.max_interval_sec == pytest.approx(0.003)
    assert stats.jitter_sec > 1e-6


def test_stats_are_zero_below_two_frames() -> None:
    """With one frame there is no interval, so every rate field is zero."""
    stats = logging_stats((_frame_at(0, 0.0),))
    assert stats.frame_count == 1
    assert stats.achieved_hz == 0.0
    assert stats.max_interval_sec == 0.0


def test_band_is_provisional_without_real_targets() -> None:
    """No tick rate and no f_max_python supplied -> provisional band."""
    band = achieved_band(PATTERN_SCHEDULER_TAP, (_frame_at(0, 0.0), _frame_at(1, 0.001)))
    assert band.provisional is True
    assert band.tick_rate_hz is None
    assert band.f_max_python_hz is None


def test_band_is_final_only_when_both_targets_supplied() -> None:
    """A band with both real figures is not provisional — reserved for rig re-verification."""
    frames = (_frame_at(0, 0.0), _frame_at(1, 0.001))
    band = achieved_band(PATTERN_SCHEDULER_TAP, frames, tick_rate_hz=1000.0, f_max_python_hz=980.0)
    assert band.provisional is False


def test_logging_did_not_outrun_ticks() -> None:
    """Equal counts pass; more frames than ticks fails."""
    assert logging_did_not_outrun_ticks(100, 100) is True
    assert logging_did_not_outrun_ticks(99, 100) is True
    assert logging_did_not_outrun_ticks(101, 100) is False
