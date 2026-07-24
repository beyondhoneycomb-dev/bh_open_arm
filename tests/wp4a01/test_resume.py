"""CG-4A-01c: resume restores optimizer/scheduler/step and the step is continuous.

FR-TRN-033. `02c` §1.1 음성 분기 ③ is explicit that LeRobot does the restoration —
our job is the `--config_path=<ckpt> --resume=true` invocation. The dummy trainer
models LeRobot's restore-and-continue, and the test reads its checkpoint back to
prove the restore happened: a run interrupted at step 5 of 10, resumed, must reach
step 10 with the optimizer's update count and the scheduler's step continuing from
5 rather than restarting at 0/1.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.training.orchestrator import JobState
from backend.training.orchestrator.checkpoints import find_last
from tests.wp4a01._support import make_orchestrator, make_spec, wait_for_checkpoint

_INTERRUPT_STEP = 5
_TOTAL_STEPS = 10


def _read_training_state(checkpoint_path: Path) -> dict[str, dict[str, object]]:
    training_state = checkpoint_path / "training_state"
    return {
        "step": json.loads((training_state / "training_step.json").read_text(encoding="utf-8")),
        "optimizer": json.loads(
            (training_state / "optimizer_state.json").read_text(encoding="utf-8")
        ),
        "scheduler": json.loads(
            (training_state / "scheduler_state.json").read_text(encoding="utf-8")
        ),
    }


def test_resume_restores_state_and_step_is_continuous(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    out = tmp_path / "run"

    # First leg: a 10-step run parked at step 5, then cancelled — the interruption.
    job = make_spec("job", out, steps=_TOTAL_STEPS, save_freq=1, hold_at_step=_INTERRUPT_STEP)
    orchestrator.submit(job)
    wait_for_checkpoint(out, _INTERRUPT_STEP)
    orchestrator.cancel("job")

    interrupted = find_last(out)
    assert interrupted is not None
    assert interrupted.step == _INTERRUPT_STEP
    before = _read_training_state(interrupted.path)
    assert before["optimizer"]["total_updates"] == _INTERRUPT_STEP

    # Second leg: resume the same job. It must continue, not restart.
    orchestrator.resume("job")
    assert orchestrator.wait("job", timeout=20.0) is JobState.DONE

    final = find_last(out)
    assert final is not None
    after = _read_training_state(final.path)

    # Step counter continuous across resume: ended at 10, not restarted to 5-or-less.
    assert after["step"]["step"] == _TOTAL_STEPS
    # Optimizer restored then advanced: 5 updates before + 5 after = 10, not 5.
    assert after["optimizer"]["total_updates"] == _TOTAL_STEPS
    # Scheduler restored then advanced to the same final step.
    assert after["scheduler"]["last_step"] == _TOTAL_STEPS


def test_resume_of_done_job_rejected(tmp_path: Path) -> None:
    from backend.training.orchestrator import OrchestratorError

    orchestrator = make_orchestrator(tmp_path)
    job = make_spec("job", tmp_path / "run", steps=2, save_freq=1)
    orchestrator.submit(job)
    assert orchestrator.wait("job", timeout=15.0) is JobState.DONE

    # DONE is terminal in the state table; resume is refused before any checkpoint
    # lookup.
    with pytest.raises(OrchestratorError):
        orchestrator.resume("job")


def test_resume_without_checkpoint_rejected(tmp_path: Path) -> None:
    from backend.training.orchestrator import OrchestratorError

    orchestrator = make_orchestrator(tmp_path)
    out = tmp_path / "run"
    out.mkdir(parents=True)  # pre-existing dir, no checkpoints inside

    # A fresh run whose output dir already exists is rejected at preflight (FAILED)
    # and never writes a checkpoint, so resuming it must fail on the missing
    # checkpoint rather than launch a run with nothing to restore.
    job = make_spec("job", out, steps=2, save_freq=1)
    orchestrator.submit(job)
    assert orchestrator.get("job").spec.state is JobState.FAILED

    with pytest.raises(OrchestratorError):
        orchestrator.resume("job")


def test_resume_builds_config_path_invocation(tmp_path: Path) -> None:
    # The orchestrator must build --config_path=<ckpt>/pretrained_model/train_config.json
    # --resume=true; the dummy asserts config_path exists and errors otherwise, so a
    # DONE resume run proves the invocation was well-formed.
    orchestrator = make_orchestrator(tmp_path)
    out = tmp_path / "run"
    job = make_spec("job", out, steps=6, save_freq=3, hold_at_step=3)
    orchestrator.submit(job)
    wait_for_checkpoint(out, 3)
    orchestrator.cancel("job")

    orchestrator.resume("job")
    assert orchestrator.wait("job", timeout=20.0) is JobState.DONE
    final = find_last(out)
    assert final is not None
    assert final.step == 6
