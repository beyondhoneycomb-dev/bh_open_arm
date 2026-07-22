"""Acceptance ③ — swapping the jog producer interrupts no scheduler tick.

A mode change (jog → some other producer, or a fresh jog session) must not pause the
CAN stream (I-1): cutting it drops a brakeless arm. The jog producer is swapped
through the Wave-1 atomic producer swap, the same mechanism the Wave-0A proof
exercises, so across many swaps every tick still writes exactly once and the only
non-accepted emission is the bracketed transition hold — never an empty, stale, or
latched gap.
"""

from __future__ import annotations

from backend.actuation import EmissionLabel
from tests.wp2a01.bench import JogSchedulerBench

_SWAPS = 2_000


def test_jog_producer_swaps_miss_no_tick() -> None:
    """Across many jog-producer swaps no tick is dropped and the only gap is the swap hold."""
    bench = JogSchedulerBench()
    first_active = bench.scheduler.active_producer_id

    bench.run_tick()  # fresh accepted before any swap
    for _ in range(_SWAPS):
        bench.begin_swap()
        bench.run_tick()  # bracketed: MODE_TRANSITION_HOLD
        bench.commit_swap()
        bench.run_tick()  # fresh accepted on the new jog producer

    expected_ticks = 1 + _SWAPS * 2

    # No missed tick: every driven tick executed and wrote exactly once.
    assert bench.scheduler.tick_index == expected_ticks
    assert bench.can_writer.write_count == expected_ticks
    assert len(bench.trace.entries) == expected_ticks

    # The only non-accepted emission is the transition hold — no empty, stale, or
    # latched gap ever appears across the swaps.
    assert bench.trace.labels() == {
        EmissionLabel.ACCEPTED_TARGET,
        EmissionLabel.MODE_TRANSITION_HOLD,
    }
    assert bench.trace.count(EmissionLabel.MODE_TRANSITION_HOLD) == _SWAPS

    # The swap really happened, atomically, and every outgoing producer was joined.
    assert bench.scheduler.active_producer_id != first_active
    assert bench.joined == _SWAPS
    assert bench.created == _SWAPS + 1


def test_mid_swap_tick_holds_and_sees_no_half_swapped_producer() -> None:
    """A tick inside the swap bracket holds and still sees the old active producer."""
    bench = JogSchedulerBench()
    bench.run_tick()

    before = bench.scheduler.active_producer_id
    bench.begin_swap()
    emission = bench.run_tick()
    assert emission.label is EmissionLabel.MODE_TRANSITION_HOLD
    assert bench.scheduler.active_producer_id == before
    assert bench.scheduler.in_transition is True

    bench.commit_swap()
    assert bench.scheduler.active_producer_id != before
    assert bench.scheduler.in_transition is False
