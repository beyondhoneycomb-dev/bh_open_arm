"""The training job queue: submit, schedule under the GPU guard, cancel, resume.

This is the FR-TRN-027/028/029/032/033 service. Its one hard invariant is
determinism of the QUEUED decision (`02c` §1.1 CG-4A-01a): a second job aimed at a
busy GPU must stay QUEUED, "예외 없이·타이밍 무관". That is bought with a single
scheduler lock, exactly the serialisation the negative branch prescribes ("큐를
단일 스케줄러 스레드로 직렬화"). Every queue mutation, every ledger read, and every
dispatch happen while holding `mLock`, so the reservation that makes a GPU busy is
committed before the next `submit` can observe it — the decision cannot depend on
thread timing.

Threading model:
- `submit`/`cancel`/`resume`/`list_jobs` run on the caller's thread and take
  `mLock` for the critical section only.
- Each running job has one monitor thread that blocks on the subprocess OUTSIDE
  the lock, then takes the lock once to finalise the job and pump the next. A
  cancel never holds the lock while joining a monitor, so the two cannot deadlock.
- The launcher's per-job reader thread is the sole writer of that job's log.

The subprocess boundary is not observability's friend (`02c` §1.1 대가): a job's
fate is read from its exit code plus "did we cancel it", which is `classify_exit`.
It is the right trade — an in-process trainer OOM would kill the CAN-owning backend
(FR-OPS-049).
"""

from __future__ import annotations

import contextlib
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from backend.training.orchestrator.checkpoints import Checkpoint, find_last
from backend.training.orchestrator.constants import (
    LOG_READER_JOIN_TIMEOUT_S,
    PROCESS_WAIT_TIMEOUT_S,
)
from backend.training.orchestrator.gpu_guard import GpuLedger
from backend.training.orchestrator.job_lineage import JobLineageRecord, JobLineageStore
from backend.training.orchestrator.launcher import (
    LaunchHandle,
    OutputDirDecision,
    TrainLauncher,
    check_output_dir,
    classify_exit,
)
from backend.training.orchestrator.logstore import LogStore
from backend.training.orchestrator.spec import (
    JobFilter,
    JobSpec,
    JobState,
    apply_filter,
    can_transition,
)

FINISHED_STATES = frozenset({JobState.DONE, JobState.CANCELLED, JobState.FAILED})

# Lineage is written when a run STOPPED with a checkpoint behind it — a cancel
# (FR-TRN-032) or a crash worth resuming — not on a clean completion, which is not
# a "stop", and not on a preflight rejection, which has no checkpoint.
_LINEAGE_ON = frozenset({JobState.CANCELLED, JobState.FAILED})


class OrchestratorError(Exception):
    """Raised for an illegal queue operation (unknown job, bad transition)."""


@dataclass
class JobRuntime:
    """A job plus the runtime bookkeeping the contract deliberately keeps off `JobSpec`.

    Attributes:
        spec: The FR-TRN-027 job record (its `state` is the source of truth).
        sequence: Submission order, for deterministic FIFO dispatch.
        allow_share: Whether the user permitted co-scheduling this job on a busy GPU.
        assigned_gpus: GPUs currently reserved for it, empty when none.
        handle: The live subprocess handle, or None.
        monitor: The thread watching the subprocess, or None.
        cancelled_by_user: Whether a cancel initiated this run's stop.
        output_dir_decision: The FR-TRN-016 three-way choice, when a fresh run hit
            an existing output dir.
        resume_checkpoint: The checkpoint a resume run was launched from, or None.
        stopped_step: The step of the last preserved checkpoint, or None.
        last_checkpoint: Path to that checkpoint, or "".
        exit_code: The subprocess return code once it has exited, or None.
    """

    spec: JobSpec
    sequence: int
    allow_share: bool = False
    assigned_gpus: tuple[int, ...] = ()
    handle: LaunchHandle | None = None
    monitor: threading.Thread | None = None
    cancelled_by_user: bool = False
    output_dir_decision: OutputDirDecision | None = None
    resume_checkpoint: Checkpoint | None = None
    stopped_step: int | None = None
    last_checkpoint: str = ""
    exit_code: int | None = None


class TrainingOrchestrator:
    """Queues and runs `lerobot-train` jobs under a deterministic GPU-exclusive guard.

    Ownership: owns the job table, the GPU ledger, and every job's monitor thread.
    The launcher, log store, and lineage store are injected collaborators it drives
    but does not own the configuration of.
    """

    def __init__(
        self,
        gpu_ids: tuple[int, ...],
        launcher: TrainLauncher,
        log_store: LogStore,
        lineage_store: JobLineageStore,
    ) -> None:
        """Create an orchestrator over a fixed GPU pool and its collaborators.

        Args:
            gpu_ids: The physical GPU ids this host schedules over.
            launcher: Builds and spawns trainer subprocesses.
            log_store: Hands out per-job log writers and reads logs back.
            lineage_store: Records where cancelled/crashed runs stopped.
        """
        self.mLock = threading.Lock()
        self.mLedger = GpuLedger(gpu_ids)
        self.mLauncher = launcher
        self.mLogStore = log_store
        self.mLineage = lineage_store
        self.mJobs: dict[str, JobRuntime] = {}
        self.mSequence = 0

    def submit(self, spec: JobSpec, allow_share: bool = False) -> JobRuntime:
        """Enqueue a job and attempt to dispatch it immediately.

        Pre-validation (`10` §4.1, before any GPU is acquired) runs the FR-TRN-016
        output-dir check: a fresh run whose output dir already exists does NOT start
        — it lands in FAILED carrying the three-way choice, never spawning a process
        and never throwing LeRobot's raw `FileExistsError`.

        Args:
            spec: The job to enqueue; its state must be QUEUED.
            allow_share: Whether the user explicitly permits co-scheduling on a busy
                GPU (the sole FR-TRN-028/072 exception).

        Returns:
            (JobRuntime) The job's runtime record.

        Raises:
            OrchestratorError: When the job id is already known or its state is not
                QUEUED.
        """
        with self.mLock:
            if spec.job_id in self.mJobs:
                raise OrchestratorError(f"job {spec.job_id} already submitted")
            if spec.state is not JobState.QUEUED:
                raise OrchestratorError(f"a submitted job must be QUEUED, got {spec.state}")
            runtime = JobRuntime(spec=spec, sequence=self.mSequence, allow_share=allow_share)
            self.mSequence += 1
            self.mJobs[spec.job_id] = runtime

            decision = check_output_dir(spec.output_dir, spec.resume)
            if decision is not None:
                runtime.output_dir_decision = decision
                self._set_state(runtime, JobState.FAILED)
                spec.ended = time.time()
                return runtime

            self._pump()
            return runtime

    def get(self, job_id: str) -> JobRuntime | None:
        """Return a job's runtime record, or None when unknown.

        Args:
            job_id: The job.

        Returns:
            (JobRuntime | None) The record, or None.
        """
        with self.mLock:
            return self.mJobs.get(job_id)

    def list_jobs(self, query: JobFilter | None = None) -> list[JobSpec]:
        """List job specs, filtered and sorted (FR-TRN-027).

        Args:
            query: The filter/sort request, or None for all jobs by creation time.

        Returns:
            (list[JobSpec]) Matching job specs in the requested order.
        """
        with self.mLock:
            specs = [runtime.spec for runtime in self.mJobs.values()]
        return apply_filter(specs, query or JobFilter())

    def set_active_session_gpus(self, gpu_ids: tuple[int, ...]) -> None:
        """Declare which GPUs live rollout/teleop sessions occupy (FR-TRN-072).

        While a GPU is declared busy by a session, no training job schedules onto it
        (barring an explicit share). Setting this may free nothing but never
        preempts a running job; it only gates future dispatch.

        Args:
            gpu_ids: GPUs a real-robot session currently holds.
        """
        with self.mLock:
            self.mLedger.set_session_gpus(gpu_ids)
            self._pump()

    def cancel(self, job_id: str) -> None:
        """Cancel a running job: SIGTERM, preserve its checkpoint, record the stop.

        Blocks until the job has finalised, so on return the job is CANCELLED and
        its stopped step is in lineage (FR-TRN-032). The lock is released before the
        monitor is joined, so cancel and the monitor cannot deadlock.

        Args:
            job_id: The job to cancel.

        Raises:
            OrchestratorError: When the job is unknown or not running.
        """
        with self.mLock:
            runtime = self.mJobs.get(job_id)
            if runtime is None:
                raise OrchestratorError(f"unknown job {job_id}")
            if runtime.spec.state is not JobState.RUNNING or runtime.handle is None:
                raise OrchestratorError(f"job {job_id} is not running (state={runtime.spec.state})")
            runtime.cancelled_by_user = True
            handle = runtime.handle
            monitor = runtime.monitor

        handle.terminate()
        if monitor is not None:
            monitor.join(timeout=PROCESS_WAIT_TIMEOUT_S + LOG_READER_JOIN_TIMEOUT_S)

    def resume(self, job_id: str) -> JobRuntime:
        """Re-enqueue a cancelled/crashed job to resume from its last checkpoint.

        Builds a fresh immutable snapshot with `resume=true` (the only sanctioned
        change to a job's configuration — a resume is a new user action, not a
        mid-run mutation) and re-queues the same job id, mirroring the `10` §4.1
        CRASHED/CANCELLED --resume--> QUEUED edge. LeRobot restores the optimizer,
        scheduler, and step from the checkpoint (`02c` §1.1 음성 분기 ③: FR-TRN-033
        asks us to state the restoration, not implement it); the launcher's job is
        the `--config_path=<ckpt> --resume=true` invocation that triggers it.

        Args:
            job_id: The job to resume.

        Returns:
            (JobRuntime) The re-queued runtime record.

        Raises:
            OrchestratorError: When the job is unknown, in a non-resumable state, or
                has no checkpoint to resume from.
        """
        with self.mLock:
            runtime = self.mJobs.get(job_id)
            if runtime is None:
                raise OrchestratorError(f"unknown job {job_id}")
            if not can_transition(runtime.spec.state, JobState.QUEUED):
                raise OrchestratorError(
                    f"job {job_id} cannot resume from state {runtime.spec.state}"
                )
            if find_last(Path(runtime.spec.output_dir)) is None:
                raise OrchestratorError(f"job {job_id} has no checkpoint to resume from")

            old = runtime.spec
            resumed_config = dict(old.config_snapshot)
            resumed_config["resume"] = True
            runtime.spec = JobSpec(
                job_id=old.job_id,
                name=old.name,
                config_snapshot=resumed_config,
                dataset=old.dataset,
                requested_gpus=old.requested_gpus,
                state=JobState.QUEUED,
                created=old.created,
                started=None,
                ended=None,
                output_dir=old.output_dir,
            )
            runtime.cancelled_by_user = False
            runtime.output_dir_decision = None
            runtime.handle = None
            runtime.monitor = None
            runtime.exit_code = None
            self._pump()
            return runtime

    def wait(self, job_id: str, timeout: float) -> JobState:
        """Block until a job reaches a finished state, returning that state.

        Robust across a resume: it tracks whichever monitor is current rather than
        capturing one, so a job re-queued mid-wait is still awaited to its next
        finish.

        Args:
            job_id: The job to await.
            timeout: Maximum seconds to wait.

        Returns:
            (JobState) The finished state (DONE, CANCELLED, or FAILED).

        Raises:
            OrchestratorError: When the job is unknown.
            TimeoutError: When the job does not finish within `timeout`.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.mLock:
                runtime = self.mJobs.get(job_id)
                if runtime is None:
                    raise OrchestratorError(f"unknown job {job_id}")
                state = runtime.spec.state
                monitor = runtime.monitor
            if state in FINISHED_STATES:
                return state
            if monitor is not None and monitor.is_alive():
                monitor.join(timeout=0.05)
            else:
                time.sleep(0.01)
        raise TimeoutError(f"job {job_id} did not finish within {timeout}s")

    def _set_state(self, runtime: JobRuntime, target: JobState) -> None:
        """Transition a job's state, enforcing the `10` §4.1 table.

        Args:
            runtime: The job to transition.
            target: The proposed next state.

        Raises:
            OrchestratorError: When the transition is not legal.
        """
        current = runtime.spec.state
        if not can_transition(current, target):
            raise OrchestratorError(
                f"illegal transition {current} -> {target} for {runtime.spec.job_id}"
            )
        runtime.spec.state = target

    def _pump(self) -> None:
        """Dispatch every queued job whose GPUs are free, in submission order.

        Must be called holding `mLock`. FIFO by submission sequence keeps dispatch
        deterministic; a job that cannot get its GPUs is simply skipped and stays
        QUEUED — that skip is the guard's whole observable effect.
        """
        queued = sorted(
            (rt for rt in self.mJobs.values() if rt.spec.state is JobState.QUEUED),
            key=lambda rt: rt.sequence,
        )
        for runtime in queued:
            gpus = self.mLedger.free_gpus(runtime.spec.requested_gpus, runtime.allow_share)
            if gpus is None:
                continue
            self._dispatch(runtime, gpus)

    def _dispatch(self, runtime: JobRuntime, gpus: tuple[int, ...]) -> None:
        """Reserve GPUs and start the trainer subprocess for one job.

        Must be called holding `mLock`. Reserving before spawning is what makes the
        GPU busy synchronously, so the next `submit` sees it (CG-4A-01a). A build or
        spawn failure returns the GPUs and lands the job in FAILED rather than
        leaking the reservation.

        Args:
            runtime: The queued job to start.
            gpus: The GPUs reserved for it.
        """
        spec = runtime.spec
        self.mLedger.reserve(gpus, spec.job_id)
        runtime.assigned_gpus = gpus
        self._set_state(runtime, JobState.PREFLIGHT)

        try:
            resume_checkpoint = find_last(Path(spec.output_dir)) if spec.resume else None
            argv = self.mLauncher.build_argv(spec, resume_checkpoint)
            writer = self.mLogStore.open_writer(spec.job_id)
            handle = self.mLauncher.launch(argv, gpus, writer)
        except Exception:
            self.mLedger.release(spec.job_id)
            runtime.assigned_gpus = ()
            spec.ended = time.time()
            self._set_state(runtime, JobState.FAILED)
            return

        runtime.handle = handle
        runtime.resume_checkpoint = resume_checkpoint
        spec.started = time.time()
        self._set_state(runtime, JobState.RUNNING)

        monitor = threading.Thread(
            target=self._monitor, args=(runtime,), name=f"monitor-{spec.job_id}", daemon=True
        )
        runtime.monitor = monitor
        monitor.start()

    def _monitor(self, runtime: JobRuntime) -> None:
        """Wait for a job's subprocess to exit, then finalise and pump the next.

        Runs on the job's own thread. It blocks on the process OUTSIDE the lock and
        drains the log reader BEFORE taking the lock, so by the time the job is
        declared finished its log is complete on disk (FR-TRN-029).

        Args:
            runtime: The running job to watch.
        """
        handle = runtime.handle
        if handle is None:
            return
        try:
            returncode = handle.wait(timeout=None)
        except Exception:
            returncode = -1
        handle.join_reader(LOG_READER_JOIN_TIMEOUT_S)

        with self.mLock:
            self._finalize(runtime, returncode)
            self._pump()

    def _finalize(self, runtime: JobRuntime, returncode: int) -> None:
        """Record a finished job's outcome and release its GPUs.

        Must be called holding `mLock`. The last checkpoint is located and its step
        recorded so a cancel's stopped step is queryable (FR-TRN-032); the GPU is
        released so the next queued job can take it.

        Args:
            runtime: The job that finished.
            returncode: Its subprocess return code.
        """
        spec = runtime.spec
        runtime.exit_code = returncode
        final_state = classify_exit(returncode, runtime.cancelled_by_user)

        last = find_last(Path(spec.output_dir))
        if last is not None:
            runtime.stopped_step = last.step
            runtime.last_checkpoint = str(last.path)

        self.mLedger.release(spec.job_id)
        runtime.assigned_gpus = ()
        spec.ended = time.time()
        self._set_state(runtime, final_state)

        if final_state in _LINEAGE_ON and last is not None:
            record = JobLineageRecord(
                job_id=spec.job_id,
                output_dir=spec.output_dir,
                stopped_step=last.step,
                last_checkpoint=str(last.path),
                ended=spec.ended or time.time(),
                final_state=final_state.value,
            )
            # A run stopped more than once (cancelled, resumed, cancelled again)
            # keeps its first lineage record; the store refuses the rewrite because
            # a stopped step is immutable.
            with contextlib.suppress(ValueError):
                self.mLineage.record(record)
