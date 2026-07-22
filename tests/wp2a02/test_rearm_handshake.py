"""Acceptance ⑤ — resume happens only through the two-step re-arm handshake.

Fault-injection form: after a latch, nothing short of the full handshake brings the
arm back. Issuing a new generation is not enough; a renewal is not enough; only an
operator confirmation clears the latch, and only then does a renewal under the new
generation resume motion. The re-arm also fully rebuilds the machinery, so a second
expiry latches again — a re-arm is a fresh start, not a permanent override.
"""

from __future__ import annotations

import pytest

from backend.actuation import EmissionLabel
from backend.deadman import RearmError, RearmHandshake, RenewalDecision
from tests.wp2a02.conftest import DeadmanHarness

_LIVE_TICKS = 20
_EXPIRY_CEILING_TICKS = 200


def _latched_harness() -> DeadmanHarness:
    """A harness driven to a latched deadman."""
    harness = DeadmanHarness()
    harness.take_deadman()
    for _ in range(_LIVE_TICKS):
        harness.tick(publish=True, renew=True)
    harness.run_until_latched(_EXPIRY_CEILING_TICKS)
    assert harness.controller.latched
    return harness


def test_issue_without_confirm_does_not_resume() -> None:
    """Issuing a new generation without operator confirm resumes nothing (⑤)."""
    harness = _latched_harness()
    original_generation = harness.controller.current_generation

    issued = harness.controller.request_rearm()
    assert issued == original_generation + 1
    assert harness.controller.awaiting_rearm_confirmation
    # The generation is not active yet, and the latch still holds.
    assert harness.controller.current_generation == original_generation
    assert harness.controller.latched

    # A renewal — even under the issued generation — is still refused, and the arm
    # stays latched.
    result = harness.renew(generation=issued)
    assert result.decision is RenewalDecision.REJECTED_LATCHED
    emission = harness.tick(publish=True, renew=False)
    assert emission.label is EmissionLabel.SAFETY_LATCH_HOLD
    assert harness.controller.latched


def test_confirm_clears_latch_and_new_generation_renewal_resumes() -> None:
    """Confirming the handshake clears the latch; a new-generation renewal resumes (⑤)."""
    harness = _latched_harness()
    original_generation = harness.controller.current_generation

    harness.controller.request_rearm()
    confirmed = harness.controller.confirm_rearm()
    assert confirmed == original_generation + 1
    assert not harness.controller.latched
    assert not harness.controller.awaiting_rearm_confirmation

    # Until a renewal under the new generation arrives, the lease is still expired, so
    # the arm holds rather than lurching — resume needs an affirmative new renewal.
    held = harness.tick(publish=True, renew=False)
    assert held.is_hold

    # A renewal under the new generation now resumes commanded motion.
    harness.reset_stream()
    result = harness.renew()
    assert result.accepted
    emission = harness.tick(publish=True, renew=True)
    assert emission.label is EmissionLabel.ACCEPTED_TARGET


def test_second_expiry_after_rearm_latches_again() -> None:
    """A re-armed deadman is a fresh start: a later expiry latches again (⑤)."""
    harness = _latched_harness()
    harness.controller.request_rearm()
    harness.controller.confirm_rearm()
    harness.reset_stream()

    # Live again under the new generation.
    for _ in range(_LIVE_TICKS):
        emission = harness.tick(publish=True, renew=True)
        assert emission.label is EmissionLabel.ACCEPTED_TARGET

    # Stop renewing: it latches once more.
    harness.run_until_latched(_EXPIRY_CEILING_TICKS)
    assert harness.controller.latched


def test_confirm_without_issue_raises() -> None:
    """A confirmation answering no offer is refused at the handshake (⑤)."""
    harness = _latched_harness()
    with pytest.raises(RearmError):
        harness.controller.confirm_rearm()
    # The latch is untouched by the rejected confirmation.
    assert harness.controller.latched


def test_handshake_generation_machine_in_isolation() -> None:
    """The generation machine issues then confirms, and refuses an empty confirm (⑤)."""
    handshake = RearmHandshake(initial_generation=3)
    assert handshake.current_generation == 3
    # Each bool state is read into a fresh local before asserting, so the static
    # checker does not carry a False-then-True narrowing across the transitions and
    # wrongly flag the later asserts as unreachable.
    awaiting = handshake.awaiting_confirmation
    assert not awaiting

    issued = handshake.issue()
    assert issued == 4
    awaiting = handshake.awaiting_confirmation
    assert awaiting
    # Issuing has not advanced the active generation.
    assert handshake.current_generation == 3

    confirmed = handshake.confirm()
    assert confirmed == 4
    assert handshake.current_generation == 4
    awaiting = handshake.awaiting_confirmation
    assert not awaiting

    with pytest.raises(RearmError):
        handshake.confirm()
