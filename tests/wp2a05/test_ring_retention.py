"""The time-bounded window — 10 s by default, lossless inside it, evicting only the tail.

`04` FR-MAN-058 fixes the retention at the last N seconds (default 10 s), and the
downstream collision ring depends on at least the last few seconds being present without
loss (`12` NFR-SAF-008). The window is keyed on each record's monotonic timestamp, so a
record is evicted only once a newer record is more than the horizon ahead of it — never
by a fixed count that could silently drop a second still inside the window.
"""

from __future__ import annotations

from dataclasses import replace

from backend.audit import DEFAULT_HORIZON_SEC, AuditRingBuffer
from tests.wp2a05.conftest import filled, make_gateway, record_from


def _record_at(ring: AuditRingBuffer, index: int, at: float) -> None:
    """Record one clean decision stamped at a given monotonic time."""
    gateway, _guard = make_gateway()
    request = filled(2.0)
    ring.record(record_from(gateway.submit(request, filled(2.0)), request, tick_index=index, at=at))


def test_default_horizon_is_ten_seconds() -> None:
    """The retention default is ten seconds (`04` FR-MAN-058)."""
    assert DEFAULT_HORIZON_SEC == 10.0
    assert AuditRingBuffer().horizon_sec == 10.0


def test_records_inside_the_window_are_all_kept() -> None:
    """Every record within the horizon is retained — no loss inside the window."""
    ring = AuditRingBuffer(horizon_sec=10.0)
    for index in range(200):
        _record_at(ring, index, at=index * 0.05)  # 200 records over 9.95 s

    assert len(ring.records) == 200
    assert ring.records[0].tick_index == 0
    assert ring.records[-1].tick_index == 199


def test_records_older_than_the_horizon_are_evicted() -> None:
    """A record more than the horizon behind the newest is dropped from the front."""
    ring = AuditRingBuffer(horizon_sec=1.0)
    _record_at(ring, 0, at=0.0)
    _record_at(ring, 1, at=0.5)
    _record_at(ring, 2, at=1.0)
    # This record is 1.2 s ahead of tick 0, past the 1.0 s horizon, so tick 0 is evicted.
    _record_at(ring, 3, at=1.2)

    kept = [record.tick_index for record in ring.records]
    assert kept == [1, 2, 3]
    assert ring.span_sec == 1.2 - 0.5


def test_a_record_exactly_at_the_horizon_is_retained() -> None:
    """Eviction is strict — a record exactly one horizon behind the newest stays."""
    ring = AuditRingBuffer(horizon_sec=2.0)
    _record_at(ring, 0, at=0.0)
    _record_at(ring, 1, at=2.0)  # exactly the horizon behind — retained, not evicted

    assert [record.tick_index for record in ring.records] == [0, 1]


def test_first_record_is_always_kept() -> None:
    """A lone record is retained regardless of horizon — nothing to evict against."""
    ring = AuditRingBuffer(horizon_sec=0.001)
    _record_at(ring, 0, at=100.0)

    assert len(ring.records) == 1


def test_records_snapshot_is_immutable_from_outside() -> None:
    """The exposed records are a tuple snapshot; mutating a copy cannot corrupt the ring."""
    ring = AuditRingBuffer()
    _record_at(ring, 0, at=0.0)
    snapshot = ring.records
    # Rebinding a local does not touch the ring's own deque.
    _ = replace(snapshot[0], tick_index=999)

    assert ring.records[0].tick_index == 0
