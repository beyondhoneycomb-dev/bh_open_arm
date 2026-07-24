"""Shared fixtures for the WP-4A-01 acceptance tests.

Every test drives a real `TrainingOrchestrator` against the dummy trainer
(`_dummy_train.py`) launched as a real subprocess, so the queue, guard, launcher,
and lineage are exercised end to end. Helpers here only assemble that wiring and
poll for observable subprocess milestones (a checkpoint appearing); they inject no
behaviour into the code under test.

Since OBS-1 the orchestrator routes every dispatch through the PREFLIGHT gate, so it
needs a `PreflightProvider`. The default here describes the committed synthetic 48-dim
fixture (`tests.wp4a02.fixtures.clean_pair`) — the real dataset these jobs stand for —
which genuinely PASSes `preflight` with no degenerate findings, so the launch-machinery
tests reach RUNNING through the real gate, not around it. Faulted providers for the
BLOCK / undecided / lineage scenarios live in the gate tests themselves.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from backend.training.lineage import LineageRecorder
from backend.training.orchestrator import (
    DatasetRef,
    JobLineageStore,
    JobSpec,
    JobState,
    LaunchLineagePlanner,
    LogStore,
    PreflightContext,
    PreflightProvider,
    TrainingOrchestrator,
    TrainLauncher,
    find_last,
)
from tests.wp4a02.fixtures import clean_pair

_DUMMY_TRAIN = Path(__file__).resolve().parent / "_dummy_train.py"
_REPO_ROOT = Path(__file__).resolve().parents[2]

# The single-GPU pool that stands in for the dev host's RTX 5080. CG-4A-01a's "two
# jobs on one GPU" is a pool of exactly one id.
SINGLE_GPU = (0,)


class CleanFixtureProvider:
    """A `PreflightProvider` that describes the clean synthetic 48-dim fixture.

    Every job resolves to the same committed clean dataset/policy pair, which PASSes
    preflight with no degenerate findings — a genuine clearance, not a fabricated one.
    The pair is built once and shared, so `context_for` is cheap under the scheduler
    lock.
    """

    def __init__(self) -> None:
        dataset, policy = clean_pair()
        self.mContext = PreflightContext(dataset=dataset, policy=policy)

    def context_for(self, spec: JobSpec) -> PreflightContext:
        """Return the clean-fixture context for any job."""
        return self.mContext


def make_orchestrator(
    tmp_path: Path,
    gpu_ids: tuple[int, ...] = SINGLE_GPU,
    preflight_provider: PreflightProvider | None = None,
    lineage_recorder: LineageRecorder | None = None,
    lineage_planner: LaunchLineagePlanner | None = None,
) -> TrainingOrchestrator:
    """Build an orchestrator whose launcher runs the dummy trainer.

    Args:
        tmp_path: The test's temp directory; logs and lineage live under it.
        gpu_ids: The GPU pool.
        preflight_provider: The PREFLIGHT-gate input source; defaults to the clean
            synthetic-fixture provider so launch-machinery tests reach RUNNING.
        lineage_recorder: WP-4A-05 recorder for launch-time lineage, or None.
        lineage_planner: Assembles that record, or None.

    Returns:
        (TrainingOrchestrator) A ready orchestrator.
    """
    launcher = TrainLauncher(base_command=(sys.executable, str(_DUMMY_TRAIN)), cwd=_REPO_ROOT)
    log_store = LogStore(tmp_path / "logs")
    lineage = JobLineageStore(tmp_path / "lineage.json")
    return TrainingOrchestrator(
        gpu_ids=gpu_ids,
        launcher=launcher,
        log_store=log_store,
        lineage_store=lineage,
        preflight_provider=preflight_provider or CleanFixtureProvider(),
        lineage_recorder=lineage_recorder,
        lineage_planner=lineage_planner,
    )


def make_spec(
    job_id: str,
    output_dir: Path,
    steps: int = 4,
    save_freq: int = 2,
    hold_at_step: int | None = None,
    requested_gpus: int = 1,
    resume: bool = False,
) -> JobSpec:
    """Assemble a JobSpec whose config snapshot drives the dummy trainer.

    The config-snapshot keys become the dummy's `--steps/--save_freq/...` flags via
    the launcher's real `build_argv`, so nothing here bypasses the launch path.

    Args:
        job_id: Job id.
        output_dir: Run output directory.
        steps: Total steps.
        save_freq: Checkpoint frequency.
        hold_at_step: If set, the dummy parks at this step until cancelled.
        requested_gpus: GPUs requested.
        resume: Whether the snapshot requests a resume.

    Returns:
        (JobSpec) A QUEUED job spec.
    """
    config: dict[str, object] = {
        "steps": steps,
        "save_freq": save_freq,
        "resume": resume,
        "policy.push_to_hub": False,
    }
    if hold_at_step is not None:
        config["hold_at_step"] = hold_at_step
    return JobSpec(
        job_id=job_id,
        name=f"job-{job_id}",
        config_snapshot=config,
        dataset=DatasetRef(repo_id="fixtures/synthetic_48dim", revision="v1.0"),
        requested_gpus=requested_gpus,
        state=JobState.QUEUED,
        created=time.time(),
        started=None,
        ended=None,
        output_dir=str(output_dir),
    )


def wait_for_checkpoint(output_dir: Path, step: int, timeout: float = 10.0) -> None:
    """Block until a checkpoint at `step` (or later) exists under `output_dir`.

    Used to synchronise on a held dummy having reached its park step, so a
    subsequent cancel observes a known stopped step deterministically.

    Args:
        output_dir: Run output directory.
        step: The step to wait for.
        timeout: Maximum seconds to wait.

    Raises:
        TimeoutError: When no such checkpoint appears in time.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        last = find_last(output_dir)
        if last is not None and last.step >= step:
            return
        time.sleep(0.01)
    raise TimeoutError(f"no checkpoint at step>={step} under {output_dir} within {timeout}s")
