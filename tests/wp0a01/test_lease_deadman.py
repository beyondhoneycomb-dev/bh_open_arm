"""Acceptance ④ — a lapsed deadman lease holds, independent of producer state.

The decisive case: the producer keeps publishing fresh targets the whole time, so
the mailbox is never stale — yet when the lease is not renewed within its window,
the expiry tick still holds, and its reason is LEASE_EXPIRED, not MAILBOX_STALE.
That a fresh target does not keep a lapsed deadman live is the independence the
gate asks for. Renewing re-arms the deadman on the next tick.
"""

from __future__ import annotations

from backend.actuation import EmissionLabel, FaultInjectionHarness, ReasonCode, TickTrace

# Five ticks of headroom before the deadman lapses; the mailbox freshness window is
# left at its default (0.05, i.e. 50 ticks), so the target stays fresh well past
# lease expiry and the two conditions cannot be confused.
LEASE_SEC = 0.005


def test_lease_expiry_holds_while_the_mailbox_is_fresh() -> None:
    """The deadman lapses and holds even though a fresh target is present every tick."""
    harness = FaultInjectionHarness(trace=TickTrace(), lease_duration_sec=LEASE_SEC)

    # Warm up: fresh target, renewed lease -> accepted.
    for _ in range(3):
        assert harness.run_tick(publish=True, renew=True).label is EmissionLabel.ACCEPTED_TARGET

    # Keep publishing fresh targets, but stop renewing the lease.
    hold = None
    for _ in range(50):
        emission = harness.run_tick(publish=True, renew=False)
        if emission.label is not EmissionLabel.ACCEPTED_TARGET:
            hold = emission
            break

    assert hold is not None, "the lease never expired within the window"
    # The hold is attributed to the deadman, not to a stale source: the mailbox was
    # published fresh on this very tick.
    assert hold.label is EmissionLabel.STALE_SOURCE_HOLD
    assert hold.reason is ReasonCode.LEASE_EXPIRED

    fresh_target = harness.mailbox.take_latest()
    assert fresh_target is not None
    age = harness.clock.now() - fresh_target.published_at
    assert age < harness.scheduler.freshness_window_sec


def test_lease_renewal_re_arms_the_deadman() -> None:
    """A renewal after expiry restores ACCEPTED on the next tick."""
    harness = FaultInjectionHarness(trace=TickTrace(), lease_duration_sec=LEASE_SEC)
    harness.run_tick(publish=True, renew=True)

    expired = None
    for _ in range(50):
        emission = harness.run_tick(publish=True, renew=False)
        if emission.reason is ReasonCode.LEASE_EXPIRED:
            expired = emission
            break
    assert expired is not None

    recovered = harness.run_tick(publish=True, renew=True)
    assert recovered.label is EmissionLabel.ACCEPTED_TARGET
