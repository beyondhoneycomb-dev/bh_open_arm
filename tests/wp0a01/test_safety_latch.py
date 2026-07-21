"""Acceptance ⑤ — a safety latch holds every tick until an operator ack.

Once latched, the scheduler emits SAFETY_LATCH_HOLD on every subsequent tick, and
nothing in the tick path clears it: not a fresh target, not a renewed lease, not a
stale source or a lapsed deadman. The only release is `acknowledge_latch`, an
explicit operator action — so before that ack, zero ticks release. The latch type
has no other exit by construction, which is what makes "0 successful releases"
provable rather than merely observed.
"""

from __future__ import annotations

from backend.actuation import EmissionLabel, FaultInjectionHarness, TickTrace

HELD_TICKS = 500


def test_latch_holds_every_tick_until_ack() -> None:
    """After a latch, every tick is SAFETY_LATCH_HOLD until the operator acks."""
    harness = FaultInjectionHarness(trace=TickTrace())
    assert harness.run_tick().label is EmissionLabel.ACCEPTED_TARGET

    harness.latch()
    for _ in range(HELD_TICKS):
        # Fresh target, renewed lease — the strongest case for accepting — still holds.
        emission = harness.run_tick(publish=True, renew=True)
        assert emission.label is EmissionLabel.SAFETY_LATCH_HOLD
        assert harness.scheduler.latch_active is True

    # Zero releases occurred before the ack.
    trace = harness.trace
    assert isinstance(trace, TickTrace)
    assert trace.count(EmissionLabel.SAFETY_LATCH_HOLD) == HELD_TICKS

    harness.acknowledge()
    assert harness.run_tick(publish=True, renew=True).label is EmissionLabel.ACCEPTED_TARGET


def test_latch_dominates_stale_and_lease_expiry() -> None:
    """Nothing outranks the latch: stale source and lapsed lease still emit the latch."""
    harness = FaultInjectionHarness(trace=TickTrace(), lease_duration_sec=0.002)
    harness.run_tick()
    harness.latch()
    # No publish, no renew: mailbox goes stale and the deadman lapses, yet the label
    # stays SAFETY_LATCH_HOLD because the latch sits at the top of the priority order.
    for _ in range(50):
        assert harness.run_tick(publish=False, renew=False).label is EmissionLabel.SAFETY_LATCH_HOLD


def test_no_release_path_other_than_acknowledge() -> None:
    """The latch exposes no release besides acknowledge — the exit is single."""
    from backend.actuation import SafetyLatch

    surface = {name for name in dir(SafetyLatch) if not name.startswith("_")}
    assert "acknowledge" in surface
    assert "release" not in surface
    assert "clear" not in surface
    assert "reset" not in surface
