"""CG-4A-01d: resume=false + existing output_dir does not start; offers 3 choices.

FR-TRN-016. The orchestrator must reproduce LeRobot's validate() collision
predicate as a pre-validation and present overwrite / new-dir / resume, never
letting the raw `FileExistsError` reach the user and never spawning a trainer.
"""

from __future__ import annotations

from pathlib import Path

from backend.training.orchestrator import JobState
from backend.training.orchestrator.checkpoints import find_last
from backend.training.orchestrator.constants import (
    CHOICE_NEW_DIR,
    CHOICE_OVERWRITE,
    CHOICE_RESUME,
)
from backend.training.orchestrator.launcher import check_output_dir
from tests.wp4a01._support import make_orchestrator, make_spec


def test_existing_output_dir_does_not_start_and_offers_three_choices(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    out = tmp_path / "run"
    out.mkdir(parents=True)  # collision: dir already exists, resume=false

    job = make_spec("job", out, steps=4, save_freq=1)
    runtime = orchestrator.submit(job)

    # It did not start: no PREFLIGHT/RUNNING, no subprocess, no checkpoint written.
    assert runtime.spec.state is JobState.FAILED
    assert runtime.handle is None
    assert find_last(out) is None

    # The three-way choice is presented, not a raw exception.
    decision = runtime.output_dir_decision
    assert decision is not None
    assert set(decision.choices) == {CHOICE_OVERWRITE, CHOICE_NEW_DIR, CHOICE_RESUME}
    assert decision.output_dir == str(out)


def test_resume_true_bypasses_the_collision(tmp_path: Path) -> None:
    # resume=true is allowed to reuse an existing dir — the whole point of resume.
    out = tmp_path / "run"
    out.mkdir(parents=True)
    assert check_output_dir(str(out), resume=True) is None
    assert check_output_dir(str(out), resume=False) is not None


def test_fresh_dir_starts_normally(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    out = tmp_path / "fresh"  # does not exist yet
    job = make_spec("job", out, steps=2, save_freq=1)
    orchestrator.submit(job)
    assert orchestrator.wait("job", timeout=15.0) is JobState.DONE
    assert orchestrator.get("job").output_dir_decision is None
