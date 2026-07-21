"""Acceptance ② — 10,000 atomic producer swaps, no missed tick, only the one gap.

Every swap is bracketed by a MODE_TRANSITION_HOLD tick; outside the brackets the
fresh target is accepted. The proof is that across all 10,000 swaps the emission
sequence contains only ACCEPTED_TARGET and MODE_TRANSITION_HOLD — never an empty
tick, never a STALE or LATCH gap — and that the tick count equals the writes, so
the scheduler never stopped across a swap.
"""

from __future__ import annotations

from backend.actuation import EmissionLabel, FaultInjectionHarness, TickTrace

SWAPS = 10_000


def test_ten_thousand_swaps_miss_no_tick_and_gap_only_on_transition() -> None:
    """Swapping producers 10,000 times leaves no missed tick and no non-transition gap."""
    harness = FaultInjectionHarness(trace=TickTrace())

    first_active = harness.scheduler.active_producer_id
    harness.run_tick()  # fresh accepted before any swap
    for _ in range(SWAPS):
        harness.begin_swap()
        harness.run_tick()  # bracketed: MODE_TRANSITION_HOLD
        harness.commit_swap()
        harness.run_tick()  # fresh accepted again on the new producer

    trace = harness.trace
    assert isinstance(trace, TickTrace)
    expected_ticks = 1 + SWAPS * 2

    # No missed tick: every driven tick executed and wrote exactly once.
    assert harness.scheduler.tick_index == expected_ticks
    assert harness.can_writer.write_count == expected_ticks
    assert len(trace.entries) == expected_ticks

    # The only non-accepted emission is the transition hold — no empty, stale or
    # latched gap ever appears across the swaps.
    assert trace.labels() == {EmissionLabel.ACCEPTED_TARGET, EmissionLabel.MODE_TRANSITION_HOLD}
    assert trace.count(EmissionLabel.MODE_TRANSITION_HOLD) == SWAPS

    # The swap actually happened, atomically, every time, and every outgoing
    # producer was joined (no leak).
    assert harness.scheduler.active_producer_id != first_active
    assert harness.swaps.joined == SWAPS
    assert harness.swaps.created == SWAPS + 1


def test_no_tick_observes_a_half_swapped_producer() -> None:
    """During a bracketed swap the active producer id is stable until commit."""
    harness = FaultInjectionHarness(trace=TickTrace())
    harness.run_tick()

    before = harness.scheduler.active_producer_id
    harness.begin_swap()
    # Mid-transition ticks still see the old active producer: the swap is one
    # atomic reassignment at commit, never a half state.
    harness.run_tick()
    assert harness.scheduler.active_producer_id == before
    assert harness.scheduler.in_transition is True

    harness.commit_swap()
    assert harness.scheduler.active_producer_id != before
    assert harness.scheduler.in_transition is False
