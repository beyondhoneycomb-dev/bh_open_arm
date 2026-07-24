"""Launch `lerobot-train` as a subprocess, and everything that framing requires.

The subprocess boundary is the load-bearing choice (`02c` §1.1 대가): running the
trainer out-of-process means an OOM kills the trainer, not the CAN-owning backend
(FR-OPS-049). The cost is that the job's state is only observable through exit code
and stdout, which is why this module also owns the log pump and the exit
classifier.

Four framing jobs live here:
- `build_argv` — the `lerobot-train` command line, fresh or resume (FR-TRN-033),
  wrapped in `accelerate launch --multi_gpu` when more than one GPU is asked for
  (FR-TRN-031). The trainer executable is injected, so a test drives the exact
  same code path against a dummy trainer that writes a fake checkpoint.
- `check_output_dir` — the FR-TRN-016 preflight that reproduces LeRobot's
  `validate()` predicate (`not resume and output_dir.is_dir()`, train.py:236-240)
  and returns a three-way choice instead of letting the raw `FileExistsError`
  reach the user.
- `launch` — spawn, pin the child to its GPUs via `CUDA_VISIBLE_DEVICES`, and tee
  its output to the log writer on a reader thread.
- `classify_exit` — turn a return code plus "did we cancel it" into a `JobState`.
"""

from __future__ import annotations

import os
import subprocess
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.training.orchestrator.checkpoints import Checkpoint
from backend.training.orchestrator.constants import (
    CUDA_DEVICES_ENV,
    OUTPUT_DIR_CHOICES,
    TERMINATION_SIGNAL,
)
from backend.training.orchestrator.logstore import LogWriter
from backend.training.orchestrator.spec import JobSpec, JobState

# Config-snapshot keys the launcher renders from `JobSpec` fields or handles
# specially (resume/config_path), so they are not double-emitted from the snapshot.
_RESERVED_CONFIG_KEYS = frozenset(
    {"resume", "config_path", "output_dir", "dataset.repo_id", "dataset.revision"}
)

_ACCELERATE_BASE = ("accelerate", "launch", "--multi_gpu")
_LEROBOT_TRAIN = "lerobot-train"


@dataclass(frozen=True)
class OutputDirDecision:
    """The FR-TRN-016 three-way choice for an existing output directory.

    Attributes:
        output_dir: The directory that already exists.
        choices: The offered resolutions: overwrite / new dir / resume.
    """

    output_dir: str
    choices: tuple[str, ...]


def _format_flag_value(value: Any) -> str:
    """Render a config value the way LeRobot/draccus expects on the CLI.

    Args:
        value: A scalar config value.

    Returns:
        (str) `true`/`false` for booleans, `str(value)` otherwise.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def check_output_dir(output_dir: str, resume: bool) -> OutputDirDecision | None:
    """Return a three-way choice when starting would collide with an existing dir.

    Mirrors LeRobot `TrainPipelineConfig.validate()` (train.py:236-240): a run with
    `resume=false` whose `output_dir` already exists must not start. Where LeRobot
    raises `FileExistsError`, this returns the structured choice so the caller can
    surface it (FR-TRN-016) rather than throw the raw exception at the user.

    Args:
        output_dir: The run output directory.
        resume: Whether the run is a resume (which is allowed to reuse the dir).

    Returns:
        (OutputDirDecision | None) The choice when a fresh run would collide, else
            None.
    """
    if not resume and Path(output_dir).is_dir():
        return OutputDirDecision(output_dir=output_dir, choices=OUTPUT_DIR_CHOICES)
    return None


def classify_exit(returncode: int, cancelled_by_user: bool) -> JobState:
    """Map a process outcome to a terminal `JobState`.

    A user cancel wins regardless of exit code: the trainer catches SIGTERM and
    exits cleanly, so the exit code alone cannot tell a cancel from a completion.
    Otherwise exit 0 is a completion and anything else — a nonzero code, a signal
    death, an OOM's 137/-9 — is a failure (`10` §4.1/§4.2).

    Args:
        returncode: The subprocess return code (negative for a killing signal).
        cancelled_by_user: Whether the orchestrator initiated the stop.

    Returns:
        (JobState) CANCELLED, DONE, or FAILED.
    """
    if cancelled_by_user:
        return JobState.CANCELLED
    if returncode == 0:
        return JobState.DONE
    return JobState.FAILED


class LaunchHandle:
    """A live training subprocess and its log-reader thread.

    Ownership/threading: created by `launch` on the scheduler thread; the reader
    thread it starts is the sole writer of the job's log. `terminate`,
    `wait`, and `join_reader` are called from the orchestrator's monitor thread. The
    handle does not decide the job's fate — it only exposes the process — so the
    single-writer discipline for state stays with the orchestrator.
    """

    def __init__(
        self, process: subprocess.Popen[str], reader: threading.Thread, log_writer: LogWriter
    ) -> None:
        self.mProcess = process
        self.mReader = reader
        self.mLogWriter = log_writer

    @property
    def pid(self) -> int:
        """The child process id."""
        return self.mProcess.pid

    @property
    def returncode(self) -> int | None:
        """The return code, or None while the process is still running."""
        return self.mProcess.returncode

    def terminate(self) -> None:
        """Send the cancellation signal (SIGTERM) so the trainer can flush.

        Never SIGKILL: FR-TRN-032 requires the last checkpoint survive a cancel,
        and only a signal the trainer can catch lets it write one.
        """
        if self.mProcess.poll() is None:
            self.mProcess.send_signal(TERMINATION_SIGNAL)

    def wait(self, timeout: float | None) -> int:
        """Wait for the process to exit and return its code.

        Args:
            timeout: Seconds to wait, or None to block.

        Returns:
            (int) The return code.

        Raises:
            subprocess.TimeoutExpired: When the timeout elapses first.
        """
        return self.mProcess.wait(timeout=timeout)

    def join_reader(self, timeout: float) -> None:
        """Join the log-reader thread and close the writer.

        Draining the reader before the job is declared finished is what makes the
        log "queryable after job end" (FR-TRN-029) rather than racing the pipe.

        Args:
            timeout: Seconds to wait for the reader to drain.
        """
        self.mReader.join(timeout=timeout)
        self.mLogWriter.close()


def _pump_logs(stream: Any, writer: LogWriter) -> None:
    """Copy every line from a process stream into the log writer until EOF.

    Args:
        stream: The subprocess text stream (stdout, with stderr merged in).
        writer: The sink to tee each line to.
    """
    for line in stream:
        writer.append(line)
    stream.close()


class TrainLauncher:
    """Builds trainer command lines and spawns them as subprocesses.

    The trainer executable is injected (`base_command`) so production runs
    `lerobot-train` while a test runs a dummy trainer through the identical build
    and spawn path — the subprocess seam is exercised, not bypassed.

    Attributes are configuration, not state; a launcher is safe to share.
    """

    def __init__(
        self, base_command: Sequence[str] = (_LEROBOT_TRAIN,), cwd: Path | None = None
    ) -> None:
        """Configure the launcher.

        Args:
            base_command: The trainer executable argv prefix.
            cwd: Working directory for spawned children, or None for the caller's.
        """
        self.mBaseCommand = tuple(base_command)
        self.mCwd = cwd

    def build_argv(self, spec: JobSpec, resume_checkpoint: Checkpoint | None) -> tuple[str, ...]:
        """Construct the trainer command line for a job.

        A resume run (FR-TRN-033) points `--config_path` at the checkpoint's
        `train_config.json` and sets `--resume=true`; a fresh run passes the
        dataset, output dir, and the flattened config snapshot. More than one
        requested GPU wraps the invocation in `accelerate launch --multi_gpu`
        (FR-TRN-031).

        Args:
            spec: The job to launch.
            resume_checkpoint: The checkpoint to resume from, or None for a fresh
                run.

        Returns:
            (tuple[str, ...]) The full argv.

        Raises:
            ValueError: When a resume is requested with no checkpoint to resume
                from.
        """
        if spec.resume:
            if resume_checkpoint is None:
                raise ValueError(f"job {spec.job_id} resumes but no checkpoint was located")
            trainer = [
                *self.mBaseCommand,
                f"--config_path={resume_checkpoint.train_config_path}",
                "--resume=true",
                f"--output_dir={spec.output_dir}",
            ]
        else:
            trainer = [
                *self.mBaseCommand,
                f"--dataset.repo_id={spec.dataset.repo_id}",
                f"--dataset.revision={spec.dataset.revision}",
                f"--output_dir={spec.output_dir}",
                "--resume=false",
                *self._snapshot_flags(spec.config_snapshot),
            ]

        if spec.requested_gpus > 1:
            return (*_ACCELERATE_BASE, f"--num_processes={spec.requested_gpus}", *trainer)
        return tuple(trainer)

    def _snapshot_flags(self, snapshot: Mapping[str, Any]) -> list[str]:
        """Render the config snapshot as `--key=value` flags, skipping reserved keys.

        Args:
            snapshot: The job's immutable config snapshot.

        Returns:
            (list[str]) One flag per non-reserved snapshot key, key-sorted so the
                argv is deterministic.
        """
        return [
            f"--{key}={_format_flag_value(snapshot[key])}"
            for key in sorted(snapshot)
            if key not in _RESERVED_CONFIG_KEYS
        ]

    def launch(
        self, argv: tuple[str, ...], gpu_ids: tuple[int, ...], log_writer: LogWriter
    ) -> LaunchHandle:
        """Spawn the trainer, pinned to its GPUs, teeing output to the log writer.

        `CUDA_VISIBLE_DEVICES` is set to exactly the reserved ids so the child sees
        only its GPUs — the process-level half of the exclusivity guard
        (FR-TRN-028) that complements the ledger's reservation.

        Args:
            argv: The command line from `build_argv`.
            gpu_ids: The GPUs reserved for this job.
            log_writer: The sink for the child's merged stdout/stderr.

        Returns:
            (LaunchHandle) The running process and its reader thread.
        """
        env = os.environ.copy()
        env[CUDA_DEVICES_ENV] = ",".join(str(gpu) for gpu in gpu_ids)
        process = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            cwd=str(self.mCwd) if self.mCwd else None,
        )
        reader = threading.Thread(target=_pump_logs, args=(process.stdout, log_writer), daemon=True)
        reader.start()
        return LaunchHandle(process=process, reader=reader, log_writer=log_writer)
