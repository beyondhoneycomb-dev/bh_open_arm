"""CG-5-08f — an observer is refused a write on *every* command path (FR-OPS-077).

Not one path — every path. The write surface is a closed enumeration; an observer is
refused on all of it, while a reader subscription is allowed. The refusal is
cross-checked against the real enforcement points (the WS control-frame authority, the
L2 lock, the command guard) so the enumeration is not a parallel truth.
"""

from __future__ import annotations

import pytest

from backend.security.command_lease import CommandDecision, CommandEnvelope, CommandGuard
from backend.security.control_lock import CommandSource, CommandSourceLock, L2Refusal
from backend.security.observer_mode import (
    ALL_COMMAND_PATHS,
    CommandPath,
    ObserverWriteError,
    assert_write_authorized,
    may_read,
    observer_refused_paths,
)
from contracts.ws import WsRole
from tests.wp5_08._support import build_deadman, take_deadman


def test_observer_is_refused_on_every_command_path() -> None:
    refused = observer_refused_paths(WsRole.OBSERVER)
    assert set(refused) == set(ALL_COMMAND_PATHS)
    # And each one really raises, not just appears in the list.
    for path in ALL_COMMAND_PATHS:
        with pytest.raises(ObserverWriteError):
            assert_write_authorized(WsRole.OBSERVER, path)


def test_operator_may_write_operator_paths_but_not_force_release() -> None:
    assert observer_refused_paths(WsRole.OPERATOR) == (CommandPath.FORCED_RELEASE,)
    # Operator commands are allowed (no raise) on the non-admin paths.
    assert_write_authorized(WsRole.OPERATOR, CommandPath.WS_COMMAND)
    assert_write_authorized(WsRole.OPERATOR, CommandPath.COMMAND_SOURCE_LOCK_ACQUIRE)
    with pytest.raises(ObserverWriteError):
        assert_write_authorized(WsRole.OPERATOR, CommandPath.FORCED_RELEASE)


def test_admin_may_force_release() -> None:
    assert_write_authorized(WsRole.ADMIN, CommandPath.FORCED_RELEASE)


def test_observer_may_read() -> None:
    assert may_read(WsRole.OBSERVER) is True


def test_observer_refused_at_the_command_guard() -> None:
    fixture = build_deadman()
    take_deadman(fixture)
    lock = CommandSourceLock(fixture.clock)
    guard = CommandGuard(fixture.controller, fixture.lease, lock, fixture.clock)
    envelope = CommandEnvelope(
        "observer-session",
        fixture.controller.current_generation,
        sequence=1,
        timestamp_mono_client=1.0,
    )
    verdict = guard.validate(envelope, WsRole.OBSERVER)
    assert verdict.decision is CommandDecision.REFUSED_NOT_OPERATOR


def test_observer_refused_at_the_l2_lock() -> None:
    fixture = build_deadman()
    lock = CommandSourceLock(fixture.clock)
    outcome = lock.acquire("observer-session", CommandSource.GUI, WsRole.OBSERVER)
    assert outcome.granted is False
    assert outcome.refusal is L2Refusal.NOT_OPERATOR
