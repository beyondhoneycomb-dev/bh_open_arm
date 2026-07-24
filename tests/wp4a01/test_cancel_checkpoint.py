"""CG-4A-01b: cancel preserves the last checkpoint and records the stopped step.

FR-TRN-032. The job is parked at a known step so the stopped step is deterministic,
then cancelled; afterward the checkpoint directory must exist and the lineage store
must return that step.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.training.orchestrator import JobState
from backend.training.orchestrator.checkpoints import find_last
from tests.wp4a01._support import make_orchestrator, make_spec, wait_for_checkpoint

_HOLD_STEP = 3


def test_cancel_preserves_checkpoint_and_records_step(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    out = tmp_path / "run"
    job = make_spec("job", out, steps=10, save_freq=1, hold_at_step=_HOLD_STEP)

    orchestrator.submit(job)
    wait_for_checkpoint(out, _HOLD_STEP)

    orchestrator.cancel("job")

    runtime = orchestrator.get("job")
    assert runtime.spec.state is JobState.CANCELLED

    # The last checkpoint survives the cancel.
    last = find_last(out)
    assert last is not None
    assert last.step == _HOLD_STEP
    assert Path(last.path).is_dir()
    assert last.train_config_path.is_file()

    # The stopped step is recorded in lineage and queryable after the job ended.
    record = orchestrator.mLineage.get("job")
    assert record is not None
    assert record.stopped_step == _HOLD_STEP
    assert record.final_state == "CANCELLED"
    assert Path(record.last_checkpoint).is_dir()


def test_cancel_of_non_running_job_is_rejected(tmp_path: Path) -> None:
    from backend.training.orchestrator import OrchestratorError

    orchestrator = make_orchestrator(tmp_path)
    with pytest.raises(OrchestratorError):
        orchestrator.cancel("nope")
