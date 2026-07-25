"""CG-5-08d — lease expiry drives a scheduler auto-hold (the U-4 mechanism).

This is the *same* code path CG-5-05d exercises: a WS delay that starves the deadman
lets it lapse, and the deadman controller's `poll()` — called once per tick before the
scheduler's `tick` — turns that lapse into an engaged safety latch via
`LatchTarget.engage_safety_latch`. This test drives that exact controller path on a
manual clock and confirms the auto-hold fires and that a command is then refused for
an expired lease. The lease is the one deadman lease, not a security-specific copy.
"""

from __future__ import annotations

from backend.security.command_lease import CommandDecision, CommandEnvelope, CommandGuard
from backend.security.control_lock import CommandSource, CommandSourceLock
from contracts.ws import WsRole
from tests.wp5_08._support import LEASE_DURATION_SEC, build_deadman, take_deadman

_SESSION = "operator-session-d"


def test_expiry_engages_the_safety_latch_via_poll() -> None:
    fixture = build_deadman()
    take_deadman(fixture)

    # A live tick first, so the monitor has seen the live->expired edge, as a real loop
    # would. No latch while live.
    fixture.clock.advance(LEASE_DURATION_SEC / 5)
    assert fixture.controller.poll() is False
    assert fixture.latch.latch_active is False

    # A WS delay (here: the clock jumping past the lease horizon) starves the renewal;
    # the next poll latches — the auto-hold.
    fixture.clock.advance(LEASE_DURATION_SEC * 3)
    engaged = fixture.controller.poll()

    assert engaged is True
    assert fixture.latch.latch_active is True
    assert fixture.latch.engage_count == 1
    # The hold is attributed to the deadman, i.e. it is the deadman expiry path (U-4),
    # the same path a WS-starved lease takes in CG-5-05d.
    assert fixture.latch.last_reason is not None
    assert fixture.latch.last_reason.gate_id == "DEADMAN"


def test_command_is_refused_after_lease_expiry() -> None:
    fixture = build_deadman()
    take_deadman(fixture)
    lock = CommandSourceLock(fixture.clock)
    assert lock.acquire(_SESSION, CommandSource.GUI, WsRole.OPERATOR).granted
    guard = CommandGuard(fixture.controller, fixture.lease, lock, fixture.clock)
    generation = fixture.controller.current_generation

    # Live: the command is accepted.
    assert guard.validate(
        CommandEnvelope(_SESSION, generation, sequence=1, timestamp_mono_client=1.0),
        WsRole.OPERATOR,
    ).accepted

    # The lease lapses and the deadman latches; the next command is refused for expiry.
    fixture.clock.advance(LEASE_DURATION_SEC / 5)
    fixture.controller.poll()
    fixture.clock.advance(LEASE_DURATION_SEC * 3)
    fixture.controller.poll()

    verdict = guard.validate(
        CommandEnvelope(_SESSION, generation, sequence=2, timestamp_mono_client=2.0),
        WsRole.OPERATOR,
    )
    assert verdict.decision is CommandDecision.REFUSED_LEASE_EXPIRED
