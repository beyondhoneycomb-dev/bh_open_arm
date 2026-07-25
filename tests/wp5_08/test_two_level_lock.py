"""CG-5-08g — L1 (one CAN fd) and L2 (one command source), each enforced alone (FR-OPS-075).

L1 is the reused Wave-0B `flock`: a second *process* is refused the CAN fd. L2 is the
command-source lock: a second *source* is refused inside one process. The point of
`FR-OPS-075` is that L1 alone cannot stop two controllers being active in one process
— L2 is what does. Both are shown here, and shown to be independent.
"""

from __future__ import annotations

from pathlib import Path

from backend.actuation.clock import ManualClock
from backend.can.lock.harness import HeldLockProcess, probe_acquire
from backend.can.lock.manager import LockManager
from backend.security.control_lock import (
    CommandSource,
    CommandSourceLock,
    L2Refusal,
    TwoLevelControlLock,
)
from contracts.ws import WsRole

_IFACE = "vcan0"


def test_l1_refuses_a_second_process(tmp_path: Path) -> None:
    lock_dir = str(tmp_path)
    with HeldLockProcess(lock_dir, [_IFACE]):
        result = probe_acquire(lock_dir, [_IFACE])
    assert result.ok is False
    assert result.blocked_iface == _IFACE
    assert result.holder is not None


def test_l2_refuses_a_second_command_source() -> None:
    lock = CommandSourceLock(ManualClock())
    first = lock.acquire("session-a", CommandSource.VR, WsRole.OPERATOR)
    second = lock.acquire("session-b", CommandSource.GUI, WsRole.OPERATOR)

    assert first.granted is True
    assert second.granted is False
    assert second.refusal is L2Refusal.ALREADY_HELD
    # The incumbent is unchanged by the refused contender.
    assert lock.holder is not None
    assert lock.holder.session_id == "session-a"


def test_l1_held_does_not_stop_two_command_sources(tmp_path: Path) -> None:
    # L1 held by THIS process — the CAN fd is owned.
    manager = LockManager(lock_dir=str(tmp_path))
    command_lock = CommandSourceLock(ManualClock())
    two_level = TwoLevelControlLock(manager, command_lock)
    assert two_level.acquire_device((_IFACE,)).ok is True

    # With L1 held, two command sources still contend — and it is L2, not L1, that
    # refuses the second one (the FR-OPS-075 point).
    assert two_level.acquire_command_source("session-a", CommandSource.VR, WsRole.OPERATOR).granted
    second = two_level.acquire_command_source("session-b", CommandSource.POLICY, WsRole.OPERATOR)
    assert second.granted is False
    assert second.refusal is L2Refusal.ALREADY_HELD

    manager.release_all()


def test_levels_are_independent_objects(tmp_path: Path) -> None:
    manager = LockManager(lock_dir=str(tmp_path))
    command_lock = CommandSourceLock(ManualClock())
    two_level = TwoLevelControlLock(manager, command_lock)
    # L2 is enforceable with no L1 ever taken.
    assert two_level.acquire_command_source("s", CommandSource.GUI, WsRole.OPERATOR).granted
    assert two_level.command_lock is command_lock
    assert two_level.device_lock is manager
