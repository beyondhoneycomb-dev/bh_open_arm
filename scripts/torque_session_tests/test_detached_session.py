"""The two properties that follow from the operator's shell having already returned.

A bash command shows its output only once it has ended, so the measurement is forked away and
the scheduling command exits immediately. Two things follow, and both are checked here: the
forked worker can never ask the operator anything, and the exit code of `--status` has to
separate "not finished yet" from "never started" — the shell that would have shown the
difference in text is gone, and the code is all a caller has left.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from scripts import torque_session as session


def _config(tmp_path: Path) -> session.SessionConfig:
    """A session config confined to a temporary tree."""
    return session.SessionConfig(
        arm=session.ARM_LEFT,
        captures_root=tmp_path,
        rid_capture_dir=tmp_path / "rid",
        operator="test",
        candump_path=None,
    )


def _write_state(tmp_path: Path, steps: dict[str, dict[str, Any]]) -> None:
    """Put a state file where `--status` reads it."""
    directory = session.session_dir(tmp_path)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / session.STATE_FILENAME).write_text(
        json.dumps({"steps": steps}, ensure_ascii=False), encoding="utf-8"
    )


def _passed_step_entries(count: int) -> dict[str, dict[str, Any]]:
    """`count` step keys, in session order, each recorded as passed."""
    return {step.key: {"passed": True, "detail": "ok"} for step in session.STEPS[:count]}


def test_no_session_is_a_different_exit_code_from_a_running_one(tmp_path: Path) -> None:
    assert session.report_status(_config(tmp_path)) == session.EXIT_NO_SESSION
    _write_state(tmp_path, _passed_step_entries(1))
    assert session.report_status(_config(tmp_path)) == session.EXIT_RUNNING


def test_a_session_that_reached_every_step_is_green(tmp_path: Path) -> None:
    _write_state(tmp_path, _passed_step_entries(len(session.STEPS)))
    assert session.report_status(_config(tmp_path)) == session.EXIT_OK


def test_extra_non_step_rows_do_not_stand_in_for_unreached_steps(tmp_path: Path) -> None:
    entries = _passed_step_entries(len(session.STEPS) - 1)
    entries["admission"] = {"passed": True, "detail": "re-admitted"}
    entries["note"] = {"passed": True, "detail": "operator note"}
    _write_state(tmp_path, entries)
    assert session.report_status(_config(tmp_path)) == session.EXIT_RUNNING


def test_the_forked_worker_cannot_read_the_operators_terminal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, Any] = {}

    def _record(argv: list[str], **kwargs: Any) -> None:
        captured["argv"] = argv
        captured["kwargs"] = kwargs

    monkeypatch.setattr(subprocess, "Popen", _record)
    session.spawn_worker(session.STEPS, _config(tmp_path), time.time())
    assert captured["kwargs"]["stdin"] is subprocess.DEVNULL
    assert captured["kwargs"]["start_new_session"] is True


def test_no_step_promises_the_operator_a_question() -> None:
    """No step may tell the operator to answer something. The worker cannot receive an answer.

    Three E-Stop measurements on this bench were lost to instructions that arrived after they
    could be acted on, which is why every instruction is in the timetable and nothing is asked
    mid-run. A step that says otherwise is an instruction the operator will wait on forever.
    """
    asking = [step.number for step in session.STEPS if "답한다" in step.operator_action]
    assert asking == []
