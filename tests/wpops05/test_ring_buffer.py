"""Acceptance ③ — the diagnostic ring buffer covers *exactly* the preceding 30 s.

The window is a contract with an exact boundary, so the boundary is what these tests pin: a
sample exactly 30 s old is retained, one an epsilon older is evicted, and the covered span is
precisely `[now - 30, now]`. A structure clock-free by design lets the tests place a sample
right on the edge and assert the outcome deterministically.
"""

from __future__ import annotations

from ops.telemetry.constants import DIAGNOSTIC_WINDOW_S
from ops.telemetry.ring_buffer import DiagnosticRingBuffer
from ops.telemetry.structured_log import LogRecord


def _record(seq: int) -> LogRecord:
    """Build a throwaway record tagged with a sequence number."""
    return LogRecord(
        monotonic_ns=seq, wall_ns=seq, subsystem="test", event="tick", fields={"seq": seq}
    )


def test_window_retains_exactly_the_preceding_30s() -> None:
    """At now=40, a 30 s window keeps samples in [10, 40] and drops everything older."""
    ring = DiagnosticRingBuffer(window_s=DIAGNOSTIC_WINDOW_S)
    for t in range(0, 45, 5):
        ring.append(float(t), _record(t))
    assert ring.coverage(now=40.0) == (10.0, 40.0)


def test_boundary_sample_at_exactly_30s_is_kept() -> None:
    """A sample exactly `window` seconds old sits on the inclusive edge and is retained."""
    ring = DiagnosticRingBuffer(window_s=30.0)
    ring.append(10.0, _record(1))  # exactly 30 s before now=40
    ring.append(25.0, _record(2))
    snap = ring.snapshot(now=40.0)
    assert [sample.t for sample in snap] == [10.0, 25.0]


def test_sample_just_over_30s_is_evicted() -> None:
    """A sample an epsilon older than the window is dropped — the boundary is not fuzzy."""
    ring = DiagnosticRingBuffer(window_s=30.0)
    ring.append(9.999, _record(1))  # older than 30 s before now=40
    ring.append(20.0, _record(2))
    snap = ring.snapshot(now=40.0)
    assert [sample.t for sample in snap] == [20.0]


def test_snapshot_reevicts_against_read_time_not_last_append() -> None:
    """A producer gone quiet still gets its stale samples evicted at read time."""
    ring = DiagnosticRingBuffer(window_s=30.0)
    ring.append(0.0, _record(1))
    ring.append(5.0, _record(2))
    # No new appends; querying far in the future must drop both.
    assert ring.snapshot(now=100.0) == ()
    assert ring.coverage(now=100.0) is None


def test_count_cap_bounds_the_ring_independent_of_window() -> None:
    """The count cap holds even when every sample is within the time window."""
    ring = DiagnosticRingBuffer(window_s=1_000_000.0, max_samples=3)
    for t in range(6):
        ring.append(float(t), _record(t))
    snap = ring.snapshot()
    assert [sample.t for sample in snap] == [3.0, 4.0, 5.0]
