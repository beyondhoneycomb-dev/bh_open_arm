"""The holder record: who owns a lock, written into the lock file, read on refusal.

`flock` itself carries no identity — a process that fails to acquire learns only
that *someone* holds the lock, not who. `01` FR-SYS-005 and `02` FR-CON-010 both
require the refusal to name the holder (PID, process name, acquire time), so the
holder writes an identity record into the lock file the moment it acquires, and a
process that is refused reads that record back. `open()` never blocks on an flock,
so the refused reader can always open the same file and read it (acceptance ①).

The record is the payload of the lock file, not a sidecar: it lives and dies with
the same inode the kernel auto-releases when the holder dies, so there is no stale
identity to garbage-collect (`02` FR-CON-010).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# The holder record is a small JSON object; this bound is far above its size and caps
# the read of a lock file that another (untrusted) process wrote.
_MAX_RECORD_BYTES = 65536


@dataclass(frozen=True)
class LockHolderReport:
    """Who holds a lock, for a refusal message or a runtime state query.

    The first four fields are the refusal contract of the WP (`{iface, holder_pid,
    holder_cmdline, lock_path}`); `acquired_at` is the acquire time `02` FR-CON-010
    additionally requires for the runtime holder query.

    Attributes:
        iface: Interface the lock guards.
        holder_pid: PID recorded by the holder, or None when the file carried no
            readable record (a holder that acquired but has not yet written).
        holder_cmdline: Holder command line recorded at acquire time.
        lock_path: Absolute path of the lock file.
        acquired_at: Unix time the holder recorded at acquisition, or None.
    """

    iface: str
    holder_pid: int | None
    holder_cmdline: str
    lock_path: str
    acquired_at: float | None

    def as_dict(self) -> dict[str, object]:
        """Return the report as a JSON-serialisable mapping.

        This is the shape the runtime lock-state query (`01` FR-SYS-009, REST + WS)
        serialises; keeping the projection here keeps that transport from reaching
        into the dataclass fields directly.

        Returns:
            (dict) The five report fields keyed by name.
        """
        return {
            "iface": self.iface,
            "holder_pid": self.holder_pid,
            "holder_cmdline": self.holder_cmdline,
            "lock_path": self.lock_path,
            "acquired_at": self.acquired_at,
        }


def current_cmdline() -> str:
    """Return this process's command line for the holder record.

    Reads `/proc/self/cmdline` on Linux (the deployment target); the NUL-separated
    argv is joined with spaces. Falls back to the interpreter argv when `/proc` is
    absent, so the record is always populated.

    Returns:
        (str) The command line, or the joined argv fallback.
    """
    proc = Path("/proc/self/cmdline")
    if proc.exists():
        raw = proc.read_bytes()
        parts = [part for part in raw.split(b"\x00") if part]
        if parts:
            return " ".join(part.decode("utf-8", "replace") for part in parts)
    return " ".join(sys.argv)


def write_holder_record(fd: int, iface: str, lock_path: Path, acquired_at: float) -> None:
    """Write this process's identity into an already-locked lock file.

    Called only after the caller holds the flock on `fd`, so the truncate-and-write
    cannot race another writer. The write is followed by `fsync` so a reader on a
    freshly acquired lock does not see a torn record.

    Args:
        fd: File descriptor of the lock file, already flocked by the caller.
        iface: Interface the lock guards.
        lock_path: Path of the lock file, recorded into the payload.
        acquired_at: Unix time of acquisition.
    """
    record = {
        "iface": iface,
        "holder_pid": os.getpid(),
        "holder_cmdline": current_cmdline(),
        "lock_path": str(lock_path),
        "acquired_at": acquired_at,
    }
    payload = json.dumps(record).encode("utf-8")
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, payload)
    os.fsync(fd)


def read_holder_record(fd: int, iface: str, lock_path: Path) -> LockHolderReport:
    """Read the holder record from a lock file a refusal just failed to acquire.

    A record may be missing or malformed only in the narrow window where the holder
    has the flock but has not yet written — the report then carries `holder_pid=None`
    rather than inventing an identity, and the refusal still stands.

    Args:
        fd: File descriptor opened on the lock file (need not be flocked).
        iface: Interface the lock guards.
        lock_path: Path of the lock file, used when the payload omits it.

    Returns:
        (LockHolderReport) The recorded holder, or a null-pid report on no record.
    """
    os.lseek(fd, 0, os.SEEK_SET)
    raw = os.read(fd, _MAX_RECORD_BYTES)
    try:
        record = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        record = {}

    pid = record.get("holder_pid")
    acquired = record.get("acquired_at")
    return LockHolderReport(
        iface=iface,
        holder_pid=int(pid) if isinstance(pid, int) else None,
        holder_cmdline=str(record.get("holder_cmdline", "")),
        lock_path=str(record.get("lock_path", lock_path)),
        acquired_at=float(acquired) if isinstance(acquired, (int, float)) else None,
    )
