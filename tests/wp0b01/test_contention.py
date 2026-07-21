"""Acceptance ① — process A holds; process B is refused and reports A's PID (100/100).

Real cross-process contention over real temp lock files. `flock` is VFS-level, so no
vcan is needed: this runs fully here. The 100 trials assert the refusal is not just a
failure but a correctly *attributed* failure — B learns exactly who holds the lock.
"""

from __future__ import annotations

from pathlib import Path

from backend.can.lock.harness import HeldLockProcess, probe_acquire

_IFACES = ("can0", "can1", "can2", "can3")
_TRIALS = 100


def test_holder_blocks_and_is_correctly_attributed(tmp_path: Path) -> None:
    """B is refused every one of 100 attempts, each naming A's PID and command line."""
    lock_dir = str(tmp_path)
    correct = 0
    with HeldLockProcess(lock_dir, _IFACES) as holder:
        for _ in range(_TRIALS):
            result = probe_acquire(lock_dir, ["can0"])
            attributed = (
                not result.ok
                and result.blocked_iface == "can0"
                and result.holder is not None
                and result.holder.holder_pid == holder.pid
                and result.holder.holder_cmdline != ""
                and result.holder.lock_path.endswith("openarm-can0.lock")
            )
            if attributed:
                correct += 1
    assert correct == _TRIALS


def test_lock_is_free_again_after_holder_exits(tmp_path: Path) -> None:
    """Once the holder process leaves, the lock is acquirable — no leaked hold."""
    lock_dir = str(tmp_path)
    with HeldLockProcess(lock_dir, _IFACES):
        assert not probe_acquire(lock_dir, ["can0"]).ok
    assert probe_acquire(lock_dir, ["can0"]).ok
