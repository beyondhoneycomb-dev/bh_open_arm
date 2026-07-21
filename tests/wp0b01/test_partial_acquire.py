"""Acceptance ② — partial acquisition (2/4) releases all and refuses; 0 residual locks.

The invariant is no partial state: if the third channel is refused, the two already
taken are let go before the manager returns. The test proves the released channels
are genuinely free afterwards, not merely dropped from a bookkeeping dict.
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path

from backend.can.lock.harness import HeldLockProcess
from backend.can.lock.manager import LockManager
from backend.can.lock.paths import normalize_lock_path

_IFACES = ("can0", "can1", "can2", "can3")


def _is_free(lock_dir: str, iface: str) -> bool:
    """Whether an interface's lock can be taken right now (nobody holds it)."""
    path = normalize_lock_path(iface, lock_dir)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return True
    except OSError:
        return False
    finally:
        os.close(fd)


def test_partial_acquire_releases_everything_and_refuses(tmp_path: Path) -> None:
    """With can2 pre-held elsewhere, a full acquire fails and holds nothing."""
    lock_dir = str(tmp_path)
    with HeldLockProcess(lock_dir, ["can2"]):
        manager = LockManager(lock_dir=lock_dir)
        result = manager.acquire_all(_IFACES)

        assert not result.ok
        assert result.blocked_iface == "can2"
        assert result.held == ()
        assert manager.held_ifaces() == ()

        # The channels taken before the refusal (can0, can1) must be free again.
        assert _is_free(lock_dir, "can0")
        assert _is_free(lock_dir, "can1")
        # can2 is still held by the other process — the refusal was real.
        assert not _is_free(lock_dir, "can2")


def test_no_residual_hold_after_refusal(tmp_path: Path) -> None:
    """After a refused all-or-nothing acquire, every channel is acquirable again."""
    lock_dir = str(tmp_path)
    with HeldLockProcess(lock_dir, ["can3"]):
        LockManager(lock_dir=lock_dir).acquire_all(_IFACES)
    # Holder gone; a fresh full acquire now succeeds, proving nothing leaked.
    manager = LockManager(lock_dir=lock_dir)
    assert manager.acquire_all(_IFACES).ok
    manager.release_all()
