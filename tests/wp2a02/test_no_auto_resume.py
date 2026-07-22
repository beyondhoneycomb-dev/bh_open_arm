"""Acceptance ③ — a valid renewal arriving after expiry does not resume motion.

This is the property that separates a real deadman from a sequence/generation check:
a renewal that is perfectly well-formed — right generation, fresh sequence, fresh age
— but arrives after the lease has expired must not bring the arm back. The latch, not
the renewal validation, is what guarantees it, and this holds it to that at two
layers: the receiver refuses the renewal (so the lease is never even renewed), and
the scheduler keeps emitting the latch hold regardless.
"""

from __future__ import annotations

from backend.actuation import EmissionLabel
from backend.deadman import RenewalDecision
from tests.wp2a02.conftest import DeadmanHarness

_LIVE_TICKS = 20
_EXPIRY_CEILING_TICKS = 200


def test_post_expiry_valid_renewal_is_refused_and_arm_stays_held() -> None:
    """A well-formed renewal after the latch is refused and does not resume motion (③)."""
    harness = DeadmanHarness()
    harness.take_deadman()
    for _ in range(_LIVE_TICKS):
        harness.tick(publish=True, renew=True)
    harness.run_until_latched(_EXPIRY_CEILING_TICKS)

    # A renewal that would be accepted on a live lease: current generation, the next
    # sequence, issued right now. It is refused solely because the deadman latched.
    result = harness.renew()
    assert result.decision is RenewalDecision.REJECTED_LATCHED
    assert result.lease is None

    # Motion does not resume even with a fresh target published every tick.
    for _ in range(10):
        emission = harness.tick(publish=True, renew=True)
        assert emission.label is EmissionLabel.SAFETY_LATCH_HOLD
    assert harness.controller.latched


def test_repeated_post_expiry_renewals_never_resume() -> None:
    """A stream of valid post-expiry renewals is uniformly refused (③)."""
    harness = DeadmanHarness()
    harness.take_deadman()
    for _ in range(_LIVE_TICKS):
        harness.tick(publish=True, renew=True)
    harness.run_until_latched(_EXPIRY_CEILING_TICKS)

    for _ in range(25):
        result = harness.renew()
        assert result.decision is RenewalDecision.REJECTED_LATCHED
        emission = harness.tick(publish=True, renew=False)
        assert emission.label is EmissionLabel.SAFETY_LATCH_HOLD


def test_renewal_on_the_expiry_tick_latches_before_it_is_judged() -> None:
    """A renewal handled after the lease has lapsed latches first, then is refused (③).

    This closes the race the naive design leaves open: if a renewal is processed on
    the tick the lease has already expired, it must not be able to renew the lease
    before expiry is noticed. `receive_renewal` latches an expired lease before it
    judges the renewal, so the renewal finds the deadman already latched.
    """
    harness = DeadmanHarness()
    harness.take_deadman()
    for _ in range(_LIVE_TICKS):
        harness.tick(publish=True, renew=True)

    # Advance past the lease duration WITHOUT calling poll(), so nothing has latched
    # yet, then hand the controller a valid renewal directly.
    for _ in range(_EXPIRY_CEILING_TICKS):
        harness.advance()
        if harness.lease.is_expired(harness.clock.now()):
            break
    # Read into a local before asserting: asserting the attribute chain directly
    # would leave the static checker believing it stays False past the renewal that
    # latches it, which it re-reads on the next line.
    latched_before_renewal = harness.controller.latched
    assert not latched_before_renewal

    result = harness.renew()
    assert result.decision is RenewalDecision.REJECTED_LATCHED
    assert harness.controller.latched
    # And the scheduler confirms the latch hold on the next tick.
    emission = harness.tick(publish=True, renew=False)
    assert emission.label is EmissionLabel.SAFETY_LATCH_HOLD
