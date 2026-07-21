"""A crashable stand-in for the control loop, driven by the crash reporter's harness.

The SIGKILL and OOM acceptance gates need a *real* process that has been emitting diagnostics
and recording state transitions, then dies uncatchably. This module is that process. It is
deliberately not the real control loop — it depends on no robot stack — but it exercises the
exact telemetry path a crash reporter reads back: a structured logger feeding a ring buffer,
a state-transition log, and an atomically republished crash context.

Run as `python -m ops.telemetry.control_loop_sim <spool_path>`. It seeds diagnostics, spools
the context, prints `READY <pid>`, and then blocks on stdin:

- an external SIGKILL (the parent's `os.kill`) models process death — no line is needed;
- the line `OOM` makes it allocate and then send *itself* SIGKILL, modelling the OOM killer,
  whose actual mechanism is SIGKILL (so the two gates converge on the same four fields);
- EOF or `STOP` is a clean shutdown (exit 0), used only to tear the harness down.
"""

from __future__ import annotations

import os
import signal
import sys
import time
from collections.abc import Callable
from pathlib import Path

from ops.telemetry.constants import (
    CONTROL_LOOP_OOM_COMMAND,
    CONTROL_LOOP_READY_PREFIX,
    CONTROL_LOOP_STOP_COMMAND,
)
from ops.telemetry.crash_context import CrashContext, atomic_write
from ops.telemetry.ring_buffer import DiagnosticRingBuffer, RingSink
from ops.telemetry.state_transition import StateTransitionLog
from ops.telemetry.structured_log import StructuredLogger

# A modest real allocation so the OOM simulation actually grows RSS before the kill, the way
# a process the OOM killer targets would have. Kept small: the fidelity that matters is the
# SIGKILL mechanism, not exhausting the host.
OOM_SIM_ALLOC_BYTES = 32 * 1024 * 1024


def seed_diagnostics(
    logger: StructuredLogger,
    ring: DiagnosticRingBuffer,
    transitions: StateTransitionLog,
    now_fn: Callable[[], float] = time.monotonic,
) -> None:
    """Emit an initial burst of diagnostics and two state transitions.

    Wired so the logger's records land in the ring: the ring is attached as a sink over the
    monotonic clock. The result is a non-empty replay window and a definite last transition,
    which is exactly what the crash report requires to be complete.

    Args:
        logger: The structured logger to emit through.
        ring: The ring buffer receiving records (attached as a sink here).
        transitions: The state-transition log to record into.
        now_fn: Monotonic-seconds source, injectable for tests.
    """
    logger.add_sink(RingSink(ring, now_fn))
    transitions.record(now_fn(), "OFFLINE", "IDLE")
    logger.emit("control", "loop_start", {"hz": 500})
    logger.emit("can", "bus_up", {"iface": "oa_fl"})
    transitions.record(now_fn(), "IDLE", "RUNNING")
    logger.emit("control", "tick", {"seq": 1})
    logger.emit("control", "tick", {"seq": 2})
    transitions.record(now_fn(), "RUNNING", "TELEOP")
    logger.emit("control", "tick", {"seq": 3})


def build_context(
    ring: DiagnosticRingBuffer,
    transitions: StateTransitionLog,
    now_fn: Callable[[], float] = time.monotonic,
) -> CrashContext:
    """Assemble the current crash context from the ring and transition log.

    Args:
        ring: The diagnostic ring buffer.
        transitions: The state-transition log.
        now_fn: Monotonic-seconds source.

    Returns:
        (CrashContext) A snapshot ready to spool.
    """
    now = now_fn()
    return CrashContext(
        pid=os.getpid(),
        captured_t=now,
        ring_samples=ring.snapshot(now),
        last_transition=transitions.last(),
    )


def _simulate_oom() -> None:
    """Grow RSS, then send this process SIGKILL — the OOM killer's actual mechanism."""
    ballast = bytearray(OOM_SIM_ALLOC_BYTES)
    # Touch every page so the allocation is resident, not just reserved.
    for offset in range(0, len(ballast), 4096):
        ballast[offset] = 1
    os.kill(os.getpid(), signal.SIGKILL)


def main(argv: list[str]) -> int:
    """Run the simulated control loop.

    Args:
        argv: `[spool_path]`.

    Returns:
        (int) Process exit code for a clean shutdown; a crash path never returns.
    """
    spool_path = Path(argv[0])
    logger = StructuredLogger()
    ring = DiagnosticRingBuffer()
    transitions = StateTransitionLog()
    seed_diagnostics(logger, ring, transitions)
    atomic_write(spool_path, build_context(ring, transitions))

    sys.stdout.write(f"{CONTROL_LOOP_READY_PREFIX}{os.getpid()}\n")
    sys.stdout.flush()

    for line in sys.stdin:
        command = line.strip()
        if command == CONTROL_LOOP_OOM_COMMAND:
            _simulate_oom()
        if command == CONTROL_LOOP_STOP_COMMAND:
            break
        logger.emit("control", "heartbeat", {"at": time.monotonic()})
        atomic_write(spool_path, build_context(ring, transitions))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
