"""CG-5-08b — a replayed command is refused (sequence/timestamp regress, FR-OPS-091).

The guard is the real one over the one deadman lease: a command is accepted only when
its `(sequence, timestamp)` strictly advances the last accepted for its `(session,
generation)`. A captured command resent unchanged regresses the sequence; a resend
with a bumped sequence but a stale clock regresses the timestamp. Both are refused.
"""

from __future__ import annotations

from backend.security.command_lease import CommandDecision, CommandEnvelope, CommandGuard
from backend.security.control_lock import CommandSource, CommandSourceLock
from contracts.ws import WsRole
from tests.wp5_08._support import build_deadman, take_deadman

_SESSION = "operator-session-1"


def _guard_with_holder() -> tuple[CommandGuard, int]:
    fixture = build_deadman()
    take_deadman(fixture)  # make the one lease live for the current generation
    lock = CommandSourceLock(fixture.clock)
    granted = lock.acquire(_SESSION, CommandSource.VR, WsRole.OPERATOR)
    assert granted.granted
    guard = CommandGuard(fixture.controller, fixture.lease, lock, fixture.clock)
    return guard, fixture.controller.current_generation


def test_fresh_commands_are_accepted_in_order() -> None:
    guard, generation = _guard_with_holder()
    first = CommandEnvelope(_SESSION, generation, sequence=1, timestamp_mono_client=1.0)
    second = CommandEnvelope(_SESSION, generation, sequence=2, timestamp_mono_client=2.0)

    assert guard.validate(first, WsRole.OPERATOR).decision is CommandDecision.ACCEPTED
    assert guard.validate(second, WsRole.OPERATOR).decision is CommandDecision.ACCEPTED


def test_resent_command_is_refused_on_sequence_regress() -> None:
    guard, generation = _guard_with_holder()
    original = CommandEnvelope(_SESSION, generation, sequence=5, timestamp_mono_client=5.0)
    assert guard.validate(original, WsRole.OPERATOR).accepted

    replay = CommandEnvelope(_SESSION, generation, sequence=5, timestamp_mono_client=5.0)
    verdict = guard.validate(replay, WsRole.OPERATOR)

    assert verdict.decision is CommandDecision.REFUSED_REPLAY_SEQUENCE
    assert not verdict.accepted


def test_bumped_sequence_with_stale_clock_is_refused_on_timestamp_regress() -> None:
    guard, generation = _guard_with_holder()
    assert guard.validate(
        CommandEnvelope(_SESSION, generation, sequence=5, timestamp_mono_client=5.0),
        WsRole.OPERATOR,
    ).accepted

    # A resend that advances the sequence but carries an older client clock — a replay
    # dressed up with a new sequence — is caught by the timestamp regress.
    stale_clock = CommandEnvelope(_SESSION, generation, sequence=6, timestamp_mono_client=4.0)
    verdict = guard.validate(stale_clock, WsRole.OPERATOR)

    assert verdict.decision is CommandDecision.REFUSED_REPLAY_TIMESTAMP


def test_refused_replay_does_not_advance_the_baseline() -> None:
    guard, generation = _guard_with_holder()
    assert guard.validate(
        CommandEnvelope(_SESSION, generation, sequence=5, timestamp_mono_client=5.0),
        WsRole.OPERATOR,
    ).accepted
    # A refused timestamp-regress must not move the baseline, so a genuine later
    # command still lands.
    guard.validate(
        CommandEnvelope(_SESSION, generation, sequence=6, timestamp_mono_client=4.0),
        WsRole.OPERATOR,
    )
    genuine = CommandEnvelope(_SESSION, generation, sequence=6, timestamp_mono_client=6.0)

    assert guard.validate(genuine, WsRole.OPERATOR).accepted
