"""Structured logger and crash-context spool — the pieces the crash report is assembled from.

The logger emits machine-shaped records; a ring sink funnels them into the diagnostic window;
and the crash context is spooled atomically so a supervisor can read it back after death. These
tests cover that path directly, independent of the subprocess crash tests.
"""

from __future__ import annotations

import json
from pathlib import Path

from ops.telemetry.crash_context import CrashContext, atomic_write, read_context
from ops.telemetry.ring_buffer import DiagnosticRingBuffer, RingSink
from ops.telemetry.state_transition import StateTransitionLog
from ops.telemetry.structured_log import LogRecord, StructuredLogger


def test_logger_emits_json_records_to_sinks() -> None:
    """Each emitted record reaches every sink and serializes to single-line JSON."""
    logger = StructuredLogger()
    captured: list[LogRecord] = []
    logger.add_sink(captured.append)
    record = logger.emit("can", "bus_up", {"iface": "oa_fl"})

    assert captured == [record]
    decoded = json.loads(record.to_json())
    assert decoded["subsystem"] == "can"
    assert decoded["event"] == "bus_up"
    assert decoded["fields"] == {"iface": "oa_fl"}
    assert "\n" not in record.to_json()


def test_ring_sink_funnels_records_into_the_window() -> None:
    """A ring sink stamps each record with the injected clock and appends it to the ring."""
    ring = DiagnosticRingBuffer(window_s=30.0)
    clock = iter([1.0, 2.0, 3.0])
    logger = StructuredLogger()
    logger.add_sink(RingSink(ring, lambda: next(clock)))
    logger.emit("control", "tick", {"seq": 1})
    logger.emit("control", "tick", {"seq": 2})

    snap = ring.snapshot()
    assert [sample.t for sample in snap] == [1.0, 2.0]
    assert [sample.record.fields["seq"] for sample in snap] == [1, 2]


def test_crash_context_spool_roundtrips_atomically(tmp_path: Path) -> None:
    """A spooled crash context reads back with its samples and last transition intact."""
    ring = DiagnosticRingBuffer(window_s=30.0)
    logger = StructuredLogger()
    logger.add_sink(RingSink(ring, _StepClock()))
    logger.emit("control", "loop_start", {"hz": 500})
    transitions = StateTransitionLog()
    transitions.record(0.0, "IDLE", "RUNNING")

    spool = tmp_path / "crash_context.json"
    atomic_write(
        spool,
        CrashContext(
            pid=4321,
            captured_t=1.0,
            ring_samples=ring.snapshot(),
            last_transition=transitions.last(),
        ),
    )

    restored = read_context(spool)
    assert restored is not None
    assert restored.pid == 4321
    assert restored.last_transition is not None
    assert restored.last_transition.to_state == "RUNNING"
    assert len(restored.ring_samples) == 1
    assert restored.ring_samples[0].record.event == "loop_start"


def test_read_context_absent_is_none(tmp_path: Path) -> None:
    """Reading a spool that was never written returns None, not an error."""
    assert read_context(tmp_path / "missing.json") is None


class _StepClock:
    """A deterministic monotonic clock that advances one second per call."""

    def __init__(self) -> None:
        self.m_now = 0.0

    def __call__(self) -> float:
        self.m_now += 1.0
        return self.m_now
