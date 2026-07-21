"""The one contract-versioned lock-path definition for the whole codebase.

Two specification requirements name different directories for the same lock:
`01` FR-SYS-005 writes `/var/lock/openarm-<iface>.lock`, `02` FR-CON-010 writes
`/run/lock/openarm-<iface>.lock`. On a systemd host these are not two locations —
`/var/lock` is a compatibility symlink to `/run/lock`, so the two forms resolve to
one inode. The disagreement is therefore reconciled to a single canonical value
here, versioned by `LOCK_PATH_CONTRACT`, and every lock path in the system is built
from `normalize_lock_path`. Any second, divergent path literal elsewhere in the lock
tree is a contract violation the static check (`staticcheck.find_divergent_lock_paths`)
rejects — that is what keeps the `01`/`02` disagreement from surviving as two copies
in code (acceptance ⑤).
"""

from __future__ import annotations

import re
from pathlib import Path

# The frozen version this path shape belongs to. A change to the directory or the
# file-name template is a contract bump, not an edit.
LOCK_PATH_CONTRACT = "CTR-LOCK@v1"

# The canonical physical lock directory (`02` FR-CON-010). `/run/lock` is the real
# tmpfs location; `/var/lock` is its legacy symlink on systemd hosts and is recorded
# below only to document the reconciliation — it is never used to construct a path.
CANONICAL_LOCK_DIR = "/run/lock"
LEGACY_LOCK_DIR_SYMLINK = "/var/lock"

LOCK_FILE_PREFIX = "openarm-"
LOCK_FILE_SUFFIX = ".lock"

# A CAN interface name is only ever a path component here (the lock is filesystem
# state, not a CAN resource), so it must not be able to escape the lock directory.
_IFACE = re.compile(r"^[A-Za-z0-9_.-]+$")


class InterfaceNameError(ValueError):
    """An interface name is unusable as a lock-file path component."""


def normalize_lock_path(iface: str, lock_dir: str = CANONICAL_LOCK_DIR) -> Path:
    """Build the single canonical lock path for one CAN interface.

    This is the only place a lock path is assembled. `lock_dir` defaults to the
    canonical directory and is overridable purely so tests (and hosts where
    `/run/lock` is not writable) can point the same shape at a temp directory —
    the file-name template never varies.

    Args:
        iface: CAN interface name, e.g. `can0`. Used as a path component only.
        lock_dir: Directory the lock file lives in. Defaults to the canonical
            `/run/lock`.

    Returns:
        (Path) `<lock_dir>/openarm-<iface>.lock`.

    Raises:
        InterfaceNameError: If `iface` is empty or contains a path separator or
            any character that could escape the lock directory.
    """
    if not _IFACE.match(iface) or iface in {".", ".."}:
        raise InterfaceNameError(f"unusable interface name for a lock path: {iface!r}")
    return Path(lock_dir) / f"{LOCK_FILE_PREFIX}{iface}{LOCK_FILE_SUFFIX}"
