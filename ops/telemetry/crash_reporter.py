"""The crash supervisor: spawn a control loop, watch it die, assemble the report.

`14` FR-OPS-024 requires crash reports be *collected automatically*. Collection lives in a
process other than the one that crashes — a dead process cannot report on itself — so this
supervisor spawns the subject, and on its death decodes the exit status and reads back the
crash context the subject left on disk. The result is a `CrashReport` carrying the four
required fields.

`12` NFR-SAF-009: this supervisor delays nothing and prevents nothing. It observes a death
that already happened and explains it. The report it builds embeds that fact.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import TracebackType

from ops.telemetry.constants import (
    CONTROL_LOOP_OOM_COMMAND,
    CONTROL_LOOP_READY_PREFIX,
    CRASH_SPOOL_FILENAME,
    SIGNAL_EXIT_OFFSET,
)
from ops.telemetry.crash_context import read_context
from ops.telemetry.crash_report import CrashReport

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SIM_MODULE = "ops.telemetry.control_loop_sim"


class SupervisedStartError(RuntimeError):
    """A supervised subject failed to reach its ready state."""


def decode_exit(returncode: int) -> tuple[int, int | None]:
    """Split a process return code into a conventional exit code and a signal.

    `subprocess` reports a signal death as a negative return code (`-signal`). This restores
    the shell convention (`128 + signal`) for the exit code and surfaces the signal number
    separately, so both fields the crash report needs are populated for a signal death.

    Args:
        returncode: The `Popen.returncode` of the exited process.

    Returns:
        (tuple[int, int | None]) `(exit_code, signal)`; `signal` is None for a plain exit.
    """
    if returncode < 0:
        terminating = -returncode
        return (SIGNAL_EXIT_OFFSET + terminating, terminating)
    return (returncode, None)


class SupervisedLoop:
    """A supervised control-loop subject, used as a context manager.

    On entry it spawns the subject and blocks until the subject prints its ready line,
    exposing the subject's PID. `inject_sigkill` and `request_oom` drive the two crash
    paths; `collect` waits for death and assembles the report. On exit it makes sure the
    subject is not left running.

    Args:
        spool_dir: Directory the subject republishes its crash context into.
    """

    def __init__(self, spool_dir: Path) -> None:
        self.m_spool_path = spool_dir / CRASH_SPOOL_FILENAME
        self.m_proc: subprocess.Popen[str] | None = None
        self.pid = -1

    def __enter__(self) -> SupervisedLoop:
        proc = subprocess.Popen(
            [sys.executable, "-m", _SIM_MODULE, str(self.m_spool_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            cwd=_REPO_ROOT,
        )
        self.m_proc = proc
        assert proc.stdout is not None
        line = proc.stdout.readline()
        if not line.startswith(CONTROL_LOOP_READY_PREFIX):
            self.close()
            raise SupervisedStartError(f"subject did not become ready: {line.strip()!r}")
        self.pid = int(line[len(CONTROL_LOOP_READY_PREFIX) :].strip())
        return self

    def inject_sigkill(self) -> None:
        """Kill the subject with SIGKILL from outside — the external-death path.

        Raises:
            RuntimeError: If the subject was never started.
        """
        if self.m_proc is None:
            raise RuntimeError("no subject to kill")
        self.m_proc.kill()

    def request_oom(self) -> None:
        """Ask the subject to simulate an OOM kill (grow RSS, then self-SIGKILL).

        Raises:
            RuntimeError: If the subject or its stdin is unavailable.
        """
        if self.m_proc is None or self.m_proc.stdin is None:
            raise RuntimeError("no subject stdin to signal OOM")
        try:
            self.m_proc.stdin.write(f"{CONTROL_LOOP_OOM_COMMAND}\n")
            self.m_proc.stdin.flush()
        except BrokenPipeError:
            # The subject may already be gone; the death itself is what we collect.
            pass

    def collect(self) -> CrashReport:
        """Wait for the subject to die and assemble its crash report.

        Returns:
            (CrashReport) The report with the decoded exit status and the spooled context.

        Raises:
            RuntimeError: If the subject was never started.
        """
        if self.m_proc is None:
            raise RuntimeError("no subject to collect")
        returncode = self.m_proc.wait()
        exit_code, terminating = decode_exit(returncode)
        context = read_context(self.m_spool_path)
        ring = context.ring_samples if context is not None else ()
        transition = context.last_transition if context is not None else None
        return CrashReport(
            pid=self.pid,
            exit_code=exit_code,
            signal=terminating,
            ring_buffer=ring,
            last_transition=transition,
            backtrace=None,
        )

    def close(self) -> None:
        """Ensure the subject is not left running."""
        if self.m_proc is None:
            return
        if self.m_proc.poll() is None:
            self.m_proc.kill()
            self.m_proc.wait()
        for stream in (self.m_proc.stdin, self.m_proc.stdout):
            if stream is not None:
                stream.close()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def report_from_return_code(
    pid: int,
    returncode: int,
    spool_path: Path,
) -> CrashReport:
    """Build a crash report from a known return code and a spool path.

    Exposed for callers that supervise a subject by other means (a systemd unit, an existing
    `Popen`) and only need the decode-plus-read-back assembly.

    Args:
        pid: The subject's PID.
        returncode: Its `Popen.returncode`.
        spool_path: Its crash-context spool file.

    Returns:
        (CrashReport) The assembled report.
    """
    exit_code, terminating = decode_exit(returncode)
    context = read_context(spool_path)
    ring = context.ring_samples if context is not None else ()
    transition = context.last_transition if context is not None else None
    return CrashReport(
        pid=pid,
        exit_code=exit_code,
        signal=terminating,
        ring_buffer=ring,
        last_transition=transition,
        backtrace=None,
    )


def default_spool_path(spool_dir: Path) -> Path:
    """Return the canonical crash-spool path within a directory.

    Args:
        spool_dir: The directory the subject spools into.

    Returns:
        (Path) `spool_dir / CRASH_SPOOL_FILENAME`.
    """
    return spool_dir / CRASH_SPOOL_FILENAME
