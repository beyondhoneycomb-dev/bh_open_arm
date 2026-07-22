"""Acceptance ④: session drift = start-vs-end q99 comparison over the frozen slop.

`02b` §6.2 WP-3B-04 ④ confirms clock drift by comparing each slot pair's q99
capture-timestamp difference at session start against session end. The distribution
math is the frozen `backend.camera.syncslop` computer, reused here; this test pins
that a widening q99 is reported as positive drift.
"""

from __future__ import annotations

from backend.camera.constants import NANOSECONDS_PER_MILLISECOND
from backend.sensing.timesync.drift import session_drift

_PERIOD_NS = 33 * NANOSECONDS_PER_MILLISECOND
_FRAMES = 60


def _pair(offset_ms: int) -> dict[str, list[int]]:
    """Two capture_ts streams where slot b trails slot a by a constant offset."""
    base = [i * _PERIOD_NS for i in range(_FRAMES)]
    return {"cam_a": base, "cam_b": [t + offset_ms * NANOSECONDS_PER_MILLISECOND for t in base]}


def test_a_widening_offset_reads_as_positive_drift() -> None:
    """q99 growing from 2 ms to 8 ms across the session is reported as +6 ms drift (④)."""
    reports = session_drift(_pair(offset_ms=2), _pair(offset_ms=8))
    assert len(reports) == 1
    report = reports[0]
    assert report.pair == ("cam_a", "cam_b")
    assert report.start_q99_ms == 2.0
    assert report.end_q99_ms == 8.0
    assert report.delta_q99_ms == 6.0
    assert report.drifted(tolerance_ms=1.0) is True
    assert report.drifted(tolerance_ms=10.0) is False


def test_a_steady_session_shows_no_drift() -> None:
    """A constant offset at both ends yields zero drift."""
    reports = session_drift(_pair(offset_ms=3), _pair(offset_ms=3))
    assert reports[0].delta_q99_ms == 0.0
    assert reports[0].drifted(tolerance_ms=0.5) is False


def test_windows_must_cover_the_same_pairs() -> None:
    """Drift is per-pair; a pair missing from one window has nothing to compare."""
    end_only_one_slot = {"cam_a": [0, 1, 2], "cam_c": [0, 1, 2]}
    try:
        session_drift(_pair(offset_ms=2), end_only_one_slot)
    except ValueError:
        return
    raise AssertionError("mismatched slot pairs across windows must be rejected")
