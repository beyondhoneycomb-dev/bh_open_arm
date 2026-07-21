"""The crash report assembled after an abnormal backend exit (`14` FR-OPS-024).

FR-OPS-024 fixes the four fields a crash report must carry: exit code, terminating signal,
the preceding-30 s diagnostic ring buffer, and the last state transition. A backtrace is
listed as "when possible" — SIGKILL and the OOM killer leave none — so it is optional and
does not count toward the required four. `has_all_required_fields` is the machine-checkable
statement of that contract.

Every rendered report embeds the NFR-SAF-009 disclaimer (`12`): the report exists to explain
a drop, never to imply the software could have stopped it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ops.telemetry.drop_disclaimer import DROP_DISCLAIMER
from ops.telemetry.ring_buffer import DiagnosticSample
from ops.telemetry.state_transition import StateTransition

# The four fields FR-OPS-024 requires, named so the completeness check and the report agree.
REQUIRED_FIELDS = ("exit_code", "signal", "ring_buffer", "last_transition")


@dataclass(frozen=True)
class CrashReport:
    """A completed crash report.

    Attributes:
        pid: The process that crashed.
        exit_code: Conventional exit status (128 + signal for a signal death).
        signal: Terminating signal number, or None for a plain non-zero exit.
        ring_buffer: The preceding-window diagnostic samples, oldest first.
        last_transition: The last recorded state transition, or None if none occurred.
        backtrace: A backtrace when one was capturable, else None.
        disclaimer: The embedded NFR-SAF-009 fact; always present.
    """

    pid: int
    exit_code: int | None
    signal: int | None
    ring_buffer: tuple[DiagnosticSample, ...]
    last_transition: StateTransition | None
    backtrace: str | None
    disclaimer: str = DROP_DISCLAIMER

    def field_presence(self) -> dict[str, bool]:
        """Report which of the four required fields are populated.

        `ring_buffer` counts as present only when non-empty: an empty replay window is the
        same failure as no window at all, so the check treats it as absent.

        Returns:
            (dict[str, bool]) One entry per required field.
        """
        return {
            "exit_code": self.exit_code is not None,
            "signal": self.signal is not None,
            "ring_buffer": len(self.ring_buffer) > 0,
            "last_transition": self.last_transition is not None,
        }

    def has_all_required_fields(self) -> bool:
        """Report whether all four FR-OPS-024 fields are present.

        Returns:
            (bool) True iff every required field is populated.
        """
        return all(self.field_presence().values())

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable form of the report.

        Returns:
            (dict[str, Any]) The report with samples and transition inlined and the
            disclaimer embedded.
        """
        return {
            "pid": self.pid,
            "exit_code": self.exit_code,
            "signal": self.signal,
            "ring_buffer": [sample.to_dict() for sample in self.ring_buffer],
            "last_transition": (
                self.last_transition.to_dict() if self.last_transition is not None else None
            ),
            "backtrace": self.backtrace,
            "disclaimer": self.disclaimer,
        }

    def render(self) -> str:
        """Render the report as human-facing text with the disclaimer embedded.

        Returns:
            (str) A multi-line report; the NFR-SAF-009 disclaimer is always included.
        """
        transition = (
            f"{self.last_transition.from_state} -> {self.last_transition.to_state} "
            f"@ {self.last_transition.t:.3f}s"
            if self.last_transition is not None
            else "(none recorded)"
        )
        coverage = "(empty)"
        if self.ring_buffer:
            coverage = f"{self.ring_buffer[0].t:.3f}s .. {self.ring_buffer[-1].t:.3f}s"
        lines = [
            f"CRASH REPORT pid={self.pid}",
            f"  exit_code: {self.exit_code}",
            f"  signal: {self.signal}",
            f"  ring_buffer: {len(self.ring_buffer)} sample(s) covering {coverage}",
            f"  last_transition: {transition}",
            f"  backtrace: {'present' if self.backtrace else '(none — uncatchable exit)'}",
            f"  NOTICE: {self.disclaimer}",
        ]
        return "\n".join(lines)
