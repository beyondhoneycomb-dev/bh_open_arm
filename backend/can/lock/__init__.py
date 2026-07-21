"""CAN channel exclusive-lock layer (WP-0B-01).

The application-level `flock` foundation `01` FR-SYS-005 / `02` FR-CON-010 require:
acquire an exclusive lock on every CAN channel before `Robot.connect()`, all-or-
nothing, and refuse startup naming the holder on failure. SocketCAN RAW has no
exclusive bind flag (`16` §10.1), so this cooperative lock is the exclusivity.

This is the surface the downstream CAN-hygiene WPs build on:

- `LockManager` — acquire-all / release-all, held-set queries, and the FR-SYS-009
  runtime lock-state snapshot. The intruder (`WP-0B-03`), double-bind (`WP-0B-04`),
  RID (`WP-0B-07`) and USB (`WP-0B-06`) WPs take a lock through this before touching
  a bus.
- `assert_lock_held` / `guarded_connect` — the ordering precondition; the measurement
  WPs assert it before publishing any measurement (lock-not-held measurement is void).
- `normalize_lock_path` / `LOCK_PATH_CONTRACT` — the single, contract-versioned lock
  path the `01`/`02` directory disagreement reconciles to.

The layer imports no CAN stack; the lock is filesystem state, taken before any socket.
"""

from __future__ import annotations

from backend.can.lock.connect_guard import (
    LockOrderingError,
    assert_lock_held,
    guarded_connect,
)
from backend.can.lock.holder import LockHolderReport
from backend.can.lock.manager import AcquireResult, LockManager, LockState
from backend.can.lock.paths import (
    CANONICAL_LOCK_DIR,
    LEGACY_LOCK_DIR_SYMLINK,
    LOCK_PATH_CONTRACT,
    InterfaceNameError,
    normalize_lock_path,
)

__all__ = [
    "CANONICAL_LOCK_DIR",
    "LEGACY_LOCK_DIR_SYMLINK",
    "LOCK_PATH_CONTRACT",
    "AcquireResult",
    "InterfaceNameError",
    "LockHolderReport",
    "LockManager",
    "LockOrderingError",
    "LockState",
    "assert_lock_held",
    "guarded_connect",
    "normalize_lock_path",
]
