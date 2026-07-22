"""Acceptance ③ (CG-2A-05c) — a safe-stop or collision dumps the ring.

On a collision the real Wave-1 `CollisionGuard` latches and calls back; wiring that
callback to the ring's `on_safety_event` dumps the whole retained window, so the seconds
before the stop survive for post-event analysis (`12` FR-SAF-065). The guard is the
genuine detection-only latch source — the dump is triggered by an actual `poll` that
latches, not by a hand-set flag. The snapshot is non-destructive: recording continues and
a later event dumps again.
"""

from __future__ import annotations

from backend.actuation import CollisionGuard, GuardCause, GuardSample, ManualClock
from backend.audit import AuditDump, AuditRingBuffer
from ops.cancel.scheduler import LatchReason
from tests.wp2a05.conftest import filled, make_gateway, record_from


class _DumpOnLatch:
    """A guard latch callback that dumps the ring — the harness's safe-stop → dump wiring.

    The guard detects and calls this; it snapshots the ring so a collision leaves the
    pre-event window on record. It holds the last dump for the test to inspect.
    """

    def __init__(self, ring: AuditRingBuffer) -> None:
        """Wire the dumper to a ring.

        Args:
            ring: The audit ring to snapshot when the guard latches.
        """
        self._ring = ring
        self.dump: AuditDump | None = None

    def __call__(self, reason: LatchReason) -> None:
        """Dump the ring in response to a guard latch.

        Args:
            reason: The latch reason the guard reports.
        """
        self.dump = self._ring.on_safety_event(reason)


def _fill_ring(ring: AuditRingBuffer, ticks: int) -> None:
    """Record `ticks` clean decisions into the ring, one per 20 ms."""
    gateway, _guard = make_gateway()
    request = filled(3.0)
    for index in range(ticks):
        result = gateway.submit(request, filled(3.0))
        ring.record(record_from(result, request, tick_index=index, at=index * 0.02))


def test_collision_poll_dumps_the_retained_window() -> None:
    """A real collision poll latches and the wired callback dumps every retained record (③)."""
    ring = AuditRingBuffer()
    dumper = _DumpOnLatch(ring)
    guard = CollisionGuard(on_latch=dumper, clock=ManualClock())
    _fill_ring(ring, ticks=5)

    # A blind poll (no observation) is a fail-closed collision latch — the arm's stop path.
    verdict = guard.poll(GuardSample(False, True, True, False))

    assert verdict.latched
    assert verdict.cause is GuardCause.OBSERVATION_MISSING
    assert dumper.dump is not None
    assert len(dumper.dump.records) == 5
    assert dumper.dump.trigger.gate_id.startswith("COLLISION_GUARD:")


def test_residual_collision_dumps_after_debounce() -> None:
    """A residual-based collision latches after debounce and dumps the ring (③)."""
    ring = AuditRingBuffer()
    dumper = _DumpOnLatch(ring)
    guard = CollisionGuard(on_latch=dumper, clock=ManualClock())
    _fill_ring(ring, ticks=3)

    # The default debounce is three consecutive over-threshold polls before a latch.
    over_threshold = GuardSample(True, True, True, True)
    verdicts = [guard.poll(over_threshold) for _ in range(3)]

    assert [v.latched for v in verdicts] == [False, False, True]
    assert verdicts[-1].cause is GuardCause.COLLISION_RESIDUAL
    assert dumper.dump is not None
    assert len(dumper.dump.records) == 3


def test_dump_carries_the_trigger_and_its_timestamp() -> None:
    """`on_safety_event` snapshots the records with the trigger reason and its time (③)."""
    ring = AuditRingBuffer()
    _fill_ring(ring, ticks=4)
    reason = LatchReason(
        gate_id="COLLISION_GUARD:collision_residual",
        previous_state="PASS",
        new_state="LATCHED",
        latched_at=1.234,
    )

    dump = ring.on_safety_event(reason)

    assert len(dump.records) == 4
    assert dump.trigger is reason
    assert dump.dumped_at == 1.234
    # Oldest-first, and spanning the ticks recorded (0.00 s .. 0.06 s).
    assert dump.records[0].tick_index == 0
    assert dump.span_sec == 4 * 0.02 - 0.02


def test_dump_is_non_destructive() -> None:
    """A dump leaves the window intact so recording continues and a later event dumps again (③)."""
    ring = AuditRingBuffer()
    _fill_ring(ring, ticks=2)
    reason = LatchReason("g", "PASS", "LATCHED", 0.5)

    first = ring.on_safety_event(reason)
    # Recording continues after the dump.
    gateway, _guard = make_gateway()
    request = filled(3.0)
    ring.record(record_from(gateway.submit(request, filled(3.0)), request, tick_index=2, at=0.04))
    second = ring.on_safety_event(reason)

    assert len(first.records) == 2
    assert len(second.records) == 3
