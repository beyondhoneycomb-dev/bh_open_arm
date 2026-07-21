"""Structured logging: every diagnostic is a JSON record, never a free-text line.

`14` FR-OPS-024 wants the crash report to replay the preceding seconds of diagnostics, and
`14` FR-OPS-006 wants those same diagnostics on the MCAP timeseries. Both need the records
to be machine-shaped, so a log record here is a dataclass with an explicit field map, not a
formatted string a reader would have to parse back apart.

The record carries two clocks. `monotonic_ns` orders events and drives the ring-buffer
window (a wall clock can step backwards under NTP and silently reorder a crash timeline);
`wall_ns` is the human-facing timestamp. Keeping both is the only way a replayed 30-second
window is both correctly ordered and readable.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

# Default emission sink: a structured logger writes nowhere unless a consumer is attached.
# The ring buffer and the MCAP writer are the two real consumers; tests attach a list sink.
LogSink = Callable[["LogRecord"], None]


@dataclass(frozen=True)
class LogRecord:
    """One structured diagnostic event.

    Attributes:
        monotonic_ns: Event time on `CLOCK_MONOTONIC`, the ordering/window clock.
        wall_ns: Event time on the wall clock, for human reading only.
        subsystem: Which producer emitted it (`can`, `control`, `camera`, ...).
        event: Short stable event name, not a sentence.
        fields: Arbitrary JSON-serializable payload for this event.
    """

    monotonic_ns: int
    wall_ns: int
    subsystem: str
    event: str
    fields: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return the record as a JSON-serializable dict.

        Returns:
            (dict[str, Any]) The record with `fields` inlined under a stable key.
        """
        return {
            "monotonic_ns": self.monotonic_ns,
            "wall_ns": self.wall_ns,
            "subsystem": self.subsystem,
            "event": self.event,
            "fields": dict(self.fields),
        }

    def to_json(self) -> str:
        """Return the record as a single-line JSON string.

        Returns:
            (str) Compact JSON with no embedded newline, so it is one log line.
        """
        return json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=True)


class StructuredLogger:
    """Emits `LogRecord`s to attached sinks, stamping both clocks at emit time.

    Ownership: the logger owns neither the sinks nor their storage; it fans a record out to
    each registered sink synchronously on the calling thread. A sink that blocks blocks the
    caller — the MCAP sink deliberately does not, it hands off to a separate process.
    """

    def __init__(self) -> None:
        self.m_sinks: list[LogSink] = []

    def add_sink(self, sink: LogSink) -> None:
        """Register a sink to receive every subsequent record.

        Args:
            sink: Callable invoked with each emitted record.
        """
        self.m_sinks.append(sink)

    def emit(self, subsystem: str, event: str, fields: Mapping[str, Any]) -> LogRecord:
        """Build a record with the current clocks and fan it out to every sink.

        Args:
            subsystem: Producer name.
            event: Stable event name.
            fields: JSON-serializable payload.

        Returns:
            (LogRecord) The record that was emitted, for the caller to also retain.
        """
        record = LogRecord(
            monotonic_ns=time.monotonic_ns(),
            wall_ns=time.time_ns(),
            subsystem=subsystem,
            event=event,
            fields=dict(fields),
        )
        for sink in self.m_sinks:
            sink(record)
        return record
