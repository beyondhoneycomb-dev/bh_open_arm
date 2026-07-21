"""Subprocess entry point that holds CAN channel locks until told to let go.

The contention harness (`harness.HeldLockProcess`) runs this as a real, separate
process so the flock contention it creates is genuine cross-process contention — the
only kind `flock` actually arbitrates. Invoked as
`python -m backend.can.lock._holder_proc <lock_dir> <iface>...`.

Protocol on stdout, one line: `ACQUIRED <pid>` once every lock is held, or
`BLOCKED <iface>` if some channel was already taken. It then blocks reading stdin
and releases on any line (graceful release) or on EOF; a SIGKILL from the parent
skips this path entirely and lets the kernel auto-release the flocks — which is the
behaviour acceptance ③ verifies.
"""

from __future__ import annotations

import os
import sys

from backend.can.lock.manager import LockManager


def main(argv: list[str]) -> int:
    """Acquire the requested locks, announce, and hold until released.

    Args:
        argv: `[lock_dir, iface, ...]`.

    Returns:
        (int) 0 on a clean acquire-hold-release cycle, 1 when a channel was blocked.
    """
    lock_dir = argv[0]
    ifaces = argv[1:]
    manager = LockManager(lock_dir=lock_dir)
    result = manager.acquire_all(ifaces)
    if not result.ok:
        sys.stdout.write(f"BLOCKED {result.blocked_iface}\n")
        sys.stdout.flush()
        return 1

    sys.stdout.write(f"ACQUIRED {os.getpid()}\n")
    sys.stdout.flush()

    # Block until the parent releases us (any line) or closes our stdin (EOF).
    sys.stdin.readline()
    manager.release_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
