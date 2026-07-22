"""Acceptance ⑥ — the reaction latches and holds until an operator acknowledges.

`FR-SAF-043`: a collision reaction latches (`latch_until_ack=true`) and never
auto-resumes (`auto_resume=false`); the only release is an explicit operator ack. The
latch is the reused Wave-1 `SafetyLatch` engaged through the scheduler, so a reaction, a
deadman release, and a cancellation all clear only the same way — an ack — and nothing
in the tick path lifts it.
"""

from __future__ import annotations

from backend.actuation import EmissionLabel, FaultInjectionHarness
from backend.reaction import (
    ReactionContext,
    ReactionExecutor,
    ReactionPolicy,
    TorqueChannel,
)

_HELD_TICKS = 300


def test_latch_holds_across_ticks_until_ack(
    context: ReactionContext, channel_available: TorqueChannel
) -> None:
    """After a reaction the latch stays held over many ticks and clears only on ack."""
    harness = FaultInjectionHarness()
    executor = ReactionExecutor(harness.scheduler, ReactionPolicy(), channel_available)
    harness.run_tick()

    executor.respond(context, now=harness.clock.now())
    assert executor.is_latched

    for _ in range(_HELD_TICKS):
        harness.advance()
        emission = harness.tick()
        assert emission.label is EmissionLabel.SAFETY_LATCH_HOLD
        assert executor.is_latched

    executor.acknowledge()
    assert not executor.is_latched


def test_renewing_the_lease_does_not_lift_the_latch(
    context: ReactionContext, channel_available: TorqueChannel
) -> None:
    """A normal lease renewal after a latch does not resume motion (no auto-resume)."""
    harness = FaultInjectionHarness()
    executor = ReactionExecutor(harness.scheduler, ReactionPolicy(), channel_available)
    harness.run_tick()
    executor.respond(context, now=harness.clock.now())

    for _ in range(_HELD_TICKS):
        harness.advance()
        harness.renew()
        harness.publish()
        emission = harness.tick()
        # A fresh, renewed, published target does not override the latch.
        assert emission.label is EmissionLabel.SAFETY_LATCH_HOLD
    assert executor.is_latched


def test_ack_then_fresh_target_resumes_only_after_ack(
    context: ReactionContext, channel_available: TorqueChannel
) -> None:
    """Only after the operator ack does a fresh target become an accepted emission."""
    harness = FaultInjectionHarness()
    executor = ReactionExecutor(harness.scheduler, ReactionPolicy(), channel_available)
    harness.run_tick()
    executor.respond(context, now=harness.clock.now())

    harness.advance()
    held = harness.tick()
    assert held.label is EmissionLabel.SAFETY_LATCH_HOLD

    executor.acknowledge()
    resumed = harness.run_tick()
    assert resumed.label is EmissionLabel.ACCEPTED_TARGET
