"""Shared fixtures for the WP-4A-01 acceptance tests.

Every test drives a real `TrainingOrchestrator` against the dummy trainer
(`_dummy_train.py`) launched as a real subprocess, so the queue, guard, launcher,
and lineage are exercised end to end. Helpers here only assemble that wiring and
poll for observable subprocess milestones (a checkpoint appearing); they inject no
behaviour into the code under test.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from backend.training.orchestrator import (
    DatasetRef,
    JobLineageStore,
    JobSpec,
    JobState,
    LogStore,
    TrainingOrchestrator,
    TrainLauncher,
    find_last,
)

_DUMMY_TRAIN = Path(__file__).resolve().parent / "_dummy_train.py"
_REPO_ROOT = Path(__file__).resolve().parents[2]

# The single-GPU pool that stands in for the dev host's RTX 5080. CG-4A-01a's "two
# jobs on one GPU" is a pool of exactly one id.
SINGLE_GPU = (0,)


def make_orchestrator(
    tmp_path: Path, gpu_ids: tuple[int, ...] = SINGLE_GPU
) -> TrainingOrchestrator:
    """Build an orchestrator whose launcher runs the dummy trainer.

    Args:
        tmp_path: The test's temp directory; logs and lineage live under it.
        gpu_ids: The GPU pool.

    Returns:
        (TrainingOrchestrator) A ready orchestrator.
    """
    launcher = TrainLauncher(base_command=(sys.executable, str(_DUMMY_TRAIN)), cwd=_REPO_ROOT)
    log_store = LogStore(tmp_path / "logs")
    lineage = JobLineageStore(tmp_path / "lineage.json")
    return TrainingOrchestrator(
        gpu_ids=gpu_ids, launcher=launcher, log_store=log_store, lineage_store=lineage
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
