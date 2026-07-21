"""Multi-process contention harness for the CAN lock manager.

`flock` only arbitrates between separate open file descriptions, so the acceptance
gates that matter (a second process is refused; a killed holder auto-releases) can
only be exercised with a real second process, not a second object in one process.
This harness spawns that process (`_holder_proc`) and gives the test a handle to it.

The harness itself opens no CAN socket and needs no vcan: `flock` is VFS-level, so a
temp directory of real lock files reproduces the full contention behaviour on any
host (which is why acceptance ①–③ run here and are not deferred).
"""

from __future__ import annotations

import signal
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType

from backend.can.lock.manager import AcquireResult, LockManager

_REPO_ROOT = Path(__file__).resolve().parents[3]
_HOLDER_MODULE = "backend.can.lock._holder_proc"
_READY_PREFIX = "ACQUIRED "
# Upper bound on how long a graceful release may take before we SIGKILL the holder.
# The holder releases the instant it reads our line, so this only guards a wedged
# child, never the normal path.
_RELEASE_TIMEOUT_S = 10


class HolderStartError(RuntimeError):
    """A holder subprocess failed to acquire the locks it was asked to hold."""


class HeldLockProcess:
    """A separate process that holds a set of CAN channel locks.

    Used as a context manager. On entry it spawns the holder and blocks until every
    requested lock is held, exposing the holder's PID; on exit it releases the holder
    gracefully. `kill` severs the process so the kernel auto-releases the flocks,
    which is how the SIGKILL acceptance is driven.

    Args:
        lock_dir: Directory the lock files live in (a temp dir under test).
        ifaces: Interfaces the holder should lock.
    """

    def __init__(self, lock_dir: str, ifaces: Sequence[str]) -> None:
        self.lock_dir = lock_dir
        self.ifaces = tuple(ifaces)
        self._proc: subprocess.Popen[str] | None = None
        self.pid = -1

    def __enter__(self) -> HeldLockProcess:
        self._proc = subprocess.Popen(
            [sys.executable, "-m", _HOLDER_MODULE, self.lock_dir, *self.ifaces],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            cwd=_REPO_ROOT,
        )
        assert self._proc.stdout is not None
        line = self._proc.stdout.readline()
        if not line.startswith(_READY_PREFIX):
            self.close()
            raise HolderStartError(f"holder did not acquire: {line.strip()!r}")
        self.pid = int(line[len(_READY_PREFIX) :].strip())
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def kill(self) -> int:
        """SIGKILL the holder and wait for it to die.

        Returns:
            (int) The holder's PID, now dead and its flocks kernel-released.
        """
        if self._proc is not None and self._proc.poll() is None:
            self._proc.send_signal(signal.SIGKILL)
            self._proc.wait()
        return self.pid

    def close(self) -> None:
        """Release the holder gracefully, or reap it if it already exited."""
        proc = self._proc
        if proc is None:
            return
        if proc.poll() is None and proc.stdin is not None:
            try:
                proc.stdin.write("release\n")
                proc.stdin.flush()
            except (BrokenPipeError, ValueError):
                proc.send_signal(signal.SIGKILL)
        try:
            proc.wait(timeout=_RELEASE_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            proc.send_signal(signal.SIGKILL)
            proc.wait()
        self._proc = None


def probe_acquire(lock_dir: str, ifaces: Sequence[str]) -> AcquireResult:
    """Attempt to acquire a set of locks from this process, releasing on success.

    The attempting side of a contention trial: it returns the raw `AcquireResult`
    (so a refusal carries the blocking holder's report) and never leaves a lock held
    — a success is released before returning so repeated trials stay independent.

    Args:
        lock_dir: Directory the lock files live in.
        ifaces: Interfaces to attempt.

    Returns:
        (AcquireResult) The attempt outcome; on `ok` the locks were released again.
    """
    manager = LockManager(lock_dir=lock_dir)
    result = manager.acquire_all(ifaces)
    if result.ok:
        manager.release_all()
    return result
