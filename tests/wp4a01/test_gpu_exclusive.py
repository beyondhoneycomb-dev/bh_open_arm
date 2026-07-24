"""CG-4A-01a: a second job on a busy GPU stays QUEUED — 100/100, timing-independent.

The determinism is structural: the reservation that makes a GPU busy is committed
under the scheduler lock before `submit` returns, so the second submission cannot
observe a free GPU regardless of thread timing. The 100-iteration loop exists to
make that claim testable rather than asserted. FR-TRN-072 (a live rollout/teleop
session blocks the GPU) is the same guard with a different busy source.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.training.orchestrator import JobState
from tests.wp4a01._support import make_orchestrator, make_spec

_ITERATIONS = 100


def test_second_job_on_one_gpu_stays_queued_deterministically(tmp_path: Path) -> None:
    for iteration in range(_ITERATIONS):
        run_dir = tmp_path / f"iter{iteration}"
        orchestrator = make_orchestrator(run_dir)

        first = make_spec("first", run_dir / "a", hold_at_step=0)
        second = make_spec("second", run_dir / "b", hold_at_step=0)

        orchestrator.submit(first)
        orchestrator.submit(second)

        assert orchestrator.get("first").spec.state is JobState.RUNNING, iteration
        assert orchestrator.get("second").spec.state is JobState.QUEUED, iteration

        # Cancelling the holder frees the GPU; the queued job is then dispatched
        # (still holding), so both are cancelled to reclaim their subprocesses.
        orchestrator.cancel("first")
        assert orchestrator.get("first").spec.state is JobState.CANCELLED, iteration
        assert orchestrator.get("second").spec.state is JobState.RUNNING, iteration
        orchestrator.cancel("second")


def test_queued_job_runs_once_the_holder_is_cancelled(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    first = make_spec("first", tmp_path / "a", hold_at_step=0)
    second = make_spec("second", tmp_path / "b", steps=2, save_freq=1)

    orchestrator.submit(first)
    orchestrator.submit(second)
    assert orchestrator.get("second").spec.state is JobState.QUEUED

    orchestrator.cancel("first")
    assert orchestrator.wait("second", timeout=15.0) is JobState.DONE


def test_active_session_blocks_scheduling_fr_trn_072(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    # A live rollout/teleop session occupies GPU 0 before any job is submitted.
    orchestrator.set_active_session_gpus((0,))

    job = make_spec("job", tmp_path / "a", hold_at_step=0)
    orchestrator.submit(job)
    assert orchestrator.get("job").spec.state is JobState.QUEUED

    # When the session ends, the guard admits the job.
    orchestrator.set_active_session_gpus(())
    assert orchestrator.get("job").spec.state is JobState.RUNNING
    orchestrator.cancel("job")


def test_explicit_share_does_not_override_a_live_session_fr_trn_072(tmp_path: Path) -> None:
    """The FR-TRN-028 share exception must not punch through the FR-TRN-072 live-robot ban.

    allow_share sanctions co-scheduling two TRAINING jobs on one GPU (FR-TRN-028); it must
    NOT let training land on a GPU a live rollout/teleop session is driving (FR-TRN-072) —
    the VRAM/SM contention that jitters the control loop is indifferent to the user's opt-in.
    So a shared job aimed at a session-held GPU stays QUEUED, exactly as the non-shared one.
    """
    orchestrator = make_orchestrator(tmp_path)
    orchestrator.set_active_session_gpus((0,))

    job = make_spec("shared", tmp_path / "a", hold_at_step=0)
    orchestrator.submit(job, allow_share=True)
    assert orchestrator.get("shared").spec.state is JobState.QUEUED

    # The share still works once the live session releases the GPU.
    orchestrator.set_active_session_gpus(())
    assert orchestrator.get("shared").spec.state is JobState.RUNNING
    orchestrator.cancel("shared")


def test_explicit_share_overrides_the_guard(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    first = make_spec("first", tmp_path / "a", hold_at_step=0)
    second = make_spec("second", tmp_path / "b", hold_at_step=0)

    orchestrator.submit(first)
    orchestrator.submit(second, allow_share=True)

    # The sole sanctioned exception: an explicit share lets both onto one GPU.
    assert orchestrator.get("second").spec.state is JobState.RUNNING
    orchestrator.cancel("first")
    orchestrator.cancel("second")


@pytest.mark.parametrize("requested", [1])
def test_single_gpu_pool_admits_one(tmp_path: Path, requested: int) -> None:
    orchestrator = make_orchestrator(tmp_path)
    job = make_spec("only", tmp_path / "a", steps=2, save_freq=1, requested_gpus=requested)
    orchestrator.submit(job)
    assert orchestrator.wait("only", timeout=15.0) is JobState.DONE
