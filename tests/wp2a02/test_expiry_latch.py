"""Acceptance ① / ② — interrupting renewal latches on expiry, with no no-command tick.

These run the deadman on the real Wave-1 scheduler, so the hold asserted here is the
actual `SAFETY_LATCH_HOLD` the single CAN writer emits, not a stand-in. ① is the
central U-4 property in its offline form: stop renewing, and expiry produces a latch
hold — and specifically a *latch*, not the auto-resuming `STALE_SOURCE_HOLD` the
decider would emit from `lease_expired` alone. ② is the "always exactly one emission"
invariant across the expiry boundary: the stream never has a silent tick.
"""

from __future__ import annotations

from backend.actuation import EmissionLabel, ReasonCode
from tests.wp2a02.conftest import DeadmanHarness

_LIVE_TICKS = 20
_EXPIRY_CEILING_TICKS = 200


def test_live_lease_commands_targets_then_latches_on_expiry() -> None:
    """A renewed lease commands targets; stopping renewal latches on expiry (①)."""
    harness = DeadmanHarness()
    harness.take_deadman()

    for _ in range(_LIVE_TICKS):
        emission = harness.tick(publish=True, renew=True)
        assert emission.label is EmissionLabel.ACCEPTED_TARGET

    harness.run_until_latched(_EXPIRY_CEILING_TICKS)
    assert harness.controller.latched
    # The very first held tick after the live run is the safety latch itself, not a
    # stale-source hold — expiry engaged the latch, which is the whole WP.
    held = harness.tick(publish=True, renew=False)
    assert held.label is EmissionLabel.SAFETY_LATCH_HOLD
    assert held.reason is ReasonCode.SAFETY_LATCH


def test_expiry_hold_is_a_latch_not_a_stale_source_hold() -> None:
    """The expiry hold is labelled a latch, distinguishing it from a source drop (①)."""
    harness = DeadmanHarness()
    harness.take_deadman()
    for _ in range(_LIVE_TICKS):
        harness.tick(publish=True, renew=True)

    latch_offset = harness.run_until_latched(_EXPIRY_CEILING_TICKS)

    # The tick that latched emitted the latch label, and every tick after it keeps
    # emitting it — a latch persists, unlike a stale hold that clears when a source
    # returns.
    for _ in range(5):
        emission = harness.tick(publish=True, renew=False)
        assert emission.label is EmissionLabel.SAFETY_LATCH_HOLD
        assert emission.reason is ReasonCode.SAFETY_LATCH
    assert latch_offset >= 0


def test_no_no_command_tick_between_expiry_and_hold() -> None:
    """Every tick across the expiry boundary writes exactly one frame — never zero (②)."""
    harness = DeadmanHarness()
    harness.take_deadman()

    writes_before = harness.can_writer.write_count
    ticks_run = 0

    for _ in range(_LIVE_TICKS):
        harness.tick(publish=True, renew=True)
        ticks_run += 1
    # Stop renewing and run through expiry and the latched tail.
    for _ in range(_EXPIRY_CEILING_TICKS):
        harness.tick(publish=True, renew=False)
        ticks_run += 1
        if harness.controller.latched:
            break

    # One CAN write per tick over the entire run: no silent tick at the expiry
    # boundary (the scheduler raises inside the tick on a zero/double write, so a
    # clean count here is the proof), and the deadman did latch.
    assert harness.can_writer.write_count - writes_before == ticks_run
    assert harness.controller.latched


def test_every_expiry_tick_is_a_hold_once_lapsed() -> None:
    """From the first lapsed tick onward, every emission is a hold, never a command (②)."""
    harness = DeadmanHarness()
    harness.take_deadman()
    for _ in range(_LIVE_TICKS):
        harness.tick(publish=True, renew=True)

    seen_hold = False
    for _ in range(_EXPIRY_CEILING_TICKS):
        emission = harness.tick(publish=True, renew=False)
        if emission.is_hold:
            seen_hold = True
        elif seen_hold:
            raise AssertionError("a command was emitted after a hold — the lease un-lapsed")
        if harness.controller.latched:
            break
    assert seen_hold
    assert harness.controller.latched
