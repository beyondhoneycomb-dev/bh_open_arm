"""The crash context: what a supervisor reads *after* the process is already dead.

SIGKILL and the OOM killer are uncatchable — the dying process runs no handler, writes no
final record. So the preceding-30 s ring buffer and the last state transition cannot be
emitted at death time; they must already be on disk. This module is that on-disk snapshot:
the control loop atomically republishes it on an interval, and the crash reporter reads back
whatever the last complete snapshot was.

Atomicity is load-bearing. A SIGKILL can land mid-write, so the writer writes a temp file
and `os.replace`s it into place — a POSIX-atomic rename — guaranteeing the reader sees either
the previous complete snapshot or the new complete one, never a torn half.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.telemetry.ring_buffer import DiagnosticSample
from ops.telemetry.state_transition import StateTransition
from ops.telemetry.structured_log import LogRecord


@dataclass(frozen=True)
class CrashContext:
    """A point-in-time snapshot of the diagnostics needed to explain a crash.

    Attributes:
        pid: The process the snapshot describes.
        captured_t: Monotonic seconds at which the snapshot was taken.
        ring_samples: The preceding-window diagnostic samples, oldest first.
        last_transition: The most recent state transition, or None if none occurred.
    """

    pid: int
    captured_t: float
    ring_samples: tuple[DiagnosticSample, ...]
    last_transition: StateTransition | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable form.

        Returns:
            (dict[str, Any]) The snapshot with samples and transition inlined.
        """
        return {
            "pid": self.pid,
            "captured_t": self.captured_t,
            "ring_samples": [sample.to_dict() for sample in self.ring_samples],
            "last_transition": (
                self.last_transition.to_dict() if self.last_transition is not None else None
            ),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> CrashContext:
        """Rebuild a context from its spooled dict.

        Args:
            data: A dict produced by `to_dict`.

        Returns:
            (CrashContext) The reconstructed snapshot.
        """
        samples = tuple(_sample_from_dict(item) for item in data.get("ring_samples", []))
        transition_data = data.get("last_transition")
        transition = (
            StateTransition.from_dict(transition_data) if transition_data is not None else None
        )
        return CrashContext(
            pid=int(data["pid"]),
            captured_t=float(data["captured_t"]),
            ring_samples=samples,
            last_transition=transition,
        )


def _sample_from_dict(item: dict[str, Any]) -> DiagnosticSample:
    """Rebuild a diagnostic sample from its spooled dict.

    Args:
        item: A dict produced by `DiagnosticSample.to_dict`.

    Returns:
        (DiagnosticSample) The reconstructed sample.
    """
    record_data = item["record"]
    record = LogRecord(
        monotonic_ns=int(record_data["monotonic_ns"]),
        wall_ns=int(record_data["wall_ns"]),
        subsystem=str(record_data["subsystem"]),
        event=str(record_data["event"]),
        fields=dict(record_data.get("fields", {})),
    )
    return DiagnosticSample(t=float(item["t"]), record=record)


def atomic_write(path: Path, context: CrashContext) -> None:
    """Atomically publish a crash context to `path`.

    Writes a sibling temp file, flushes and fsyncs it, then renames it over `path`. A
    SIGKILL at any instant leaves either the prior snapshot or this one intact.

    Args:
        path: Destination spool path.
        context: The snapshot to publish.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    payload = json.dumps(context.to_dict(), separators=(",", ":"), sort_keys=True)
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    # Path.replace is an atomic rename (os.replace); a SIGKILL mid-write leaves either the
    # prior complete snapshot or this one, never a torn file.
    tmp.replace(path)


def read_context(path: Path) -> CrashContext | None:
    """Read back the last complete crash context, if any.

    Args:
        path: Spool path previously written by `atomic_write`.

    Returns:
        (CrashContext | None) The snapshot, or None if the spool is absent or unreadable
        as complete JSON (a partial write is treated as "no snapshot", never guessed at).
    """
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return CrashContext.from_dict(data)
