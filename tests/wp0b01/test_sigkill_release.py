"""Acceptance ③ — SIGKILL the holder; the kernel auto-releases the flock.

`02` FR-CON-010 relies on this: a process that dies takes its locks with it, so there
is no stale-lock reaper to build. SIGKILL is the strongest test — the holder gets no
chance to run cleanup, so a lock that frees afterward proves the kernel, not the
application, released it.
"""

from __future__ import annotations

from pathlib import Path

from backend.can.lock.harness import HeldLockProcess, probe_acquire


def test_sigkill_holder_auto_releases(tmp_path: Path) -> None:
    """A killed holder's lock is acquirable immediately after it dies."""
    lock_dir = str(tmp_path)
    holder = HeldLockProcess(lock_dir, ["can0"])
    holder.__enter__()

    assert not probe_acquire(lock_dir, ["can0"]).ok  # held while alive

    holder.kill()  # no cleanup path runs; kernel must release

    assert probe_acquire(lock_dir, ["can0"]).ok


def test_sigkill_frees_every_channel_a_holder_held(tmp_path: Path) -> None:
    """Killing a multi-channel holder frees all of its channels at once."""
    lock_dir = str(tmp_path)
    ifaces = ["can0", "can1", "can2", "can3"]
    holder = HeldLockProcess(lock_dir, ifaces)
    holder.__enter__()
    holder.kill()

    manager = probe_acquire(lock_dir, ifaces)
    assert manager.ok
