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

# Ways a Python module can read from whoever ran it. None of them may appear in the runner: the
# scheduling command has already returned by the time a step runs, so a prompt reaches a terminal
# that is no longer showing this program's output.
INPUT_READERS = ("input(", "sys.stdin", "getpass", "fileinput")

# Ways a step's text could tell the operator to send something back.
ANSWER_PROMISES = ("답한다", "응답한다", "대답한다", "입력한다", "?")

# The step whose content is the torque coming back down. Selected on its own below because it is
# the only proper subset of a two-step table that is allowed to be scheduled.
RELEASE_STEP = 2

# Far enough ahead that the epoch handed to the fork cannot be confused with the fork's own clock.
DISTANT_START_SECONDS = 3600.0

# The epoch crosses the argv as text with millisecond precision, so it comes back rounded.
EPOCH_TOLERANCE_SECONDS = 0.01


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


def _spawned(
    monkeypatch: pytest.MonkeyPatch,
    steps: tuple[session.Step, ...],
    tmp_path: Path,
    start_epoch: float,
) -> dict[str, Any]:
    """Run `spawn_worker` with the fork replaced, and return the call it would have made."""
    captured: dict[str, Any] = {}

    def _record(argv: list[str], **kwargs: Any) -> None:
        captured["argv"] = argv
        captured["kwargs"] = kwargs

    monkeypatch.setattr(subprocess, "Popen", _record)
    session.spawn_worker(steps, _config(tmp_path), start_epoch)
    return captured


def test_the_forked_worker_cannot_read_the_operators_terminal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = _spawned(monkeypatch, session.STEPS, tmp_path, time.time())
    assert captured["kwargs"]["stdin"] is subprocess.DEVNULL
    assert captured["kwargs"]["start_new_session"] is True


def test_the_forked_worker_runs_only_the_steps_the_timetable_showed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The operator consented to a timetable, and the worker's argv is what actually runs.

    A worker that is handed no selection runs the whole table, engage included, after a person was
    shown one step and told when it ends. The two have to be the same list, which only shows on a
    selection narrower than the table: the release on its own.
    """
    selection = tuple(step for step in session.STEPS if step.number == RELEASE_STEP)
    assert len(selection) == 1
    assert len(selection) < len(session.STEPS)
    argv = _spawned(monkeypatch, selection, tmp_path, time.time())["argv"]
    assert "--steps" in argv
    assert argv[argv.index("--steps") + 1] == str(RELEASE_STEP)
    assert "--worker" in argv


def test_the_worker_is_told_which_arm_and_which_operator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    argv = _spawned(monkeypatch, session.STEPS, tmp_path, time.time())["argv"]
    assert argv[argv.index("--arm") + 1] == config.arm
    assert argv[argv.index("--operator") + 1] == config.operator
    assert argv[argv.index("--captures") + 1] == str(config.captures_root)


def test_the_worker_is_told_the_instant_the_timetable_promised(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The operator read wall-clock instants derived from this epoch, not from the fork's clock.

    A worker left to call `time.time()` itself starts its schedule whenever it happens to come
    up, and every instant the operator was shown moves by however long the fork took.
    """
    start_epoch = time.time() + DISTANT_START_SECONDS
    argv = _spawned(monkeypatch, session.STEPS, tmp_path, start_epoch)["argv"]
    passed = float(argv[argv.index("--start-epoch") + 1])
    assert passed == pytest.approx(start_epoch, abs=EPOCH_TOLERANCE_SECONDS)
    assert passed - time.time() > 0


def test_the_runner_has_no_channel_to_receive_an_answer_on() -> None:
    """Nothing the operator is told to do may require them to reply.

    Three E-Stop measurements on this bench were lost to instructions that arrived after they
    could be acted on — the operator's shell had already returned, and the process that would
    have read their answer was detached with its stdin closed. So the property is enforced by
    there being no way to ask: the runner reads no input stream anywhere, and any code that grew
    one would be a question printed into a terminal nobody is watching.
    """
    source = Path(session.__file__).read_text(encoding="utf-8")
    reachable = [reader for reader in INPUT_READERS if reader in source]
    assert reachable == []


def test_no_step_promises_the_operator_a_question() -> None:
    """A step whose text asks for an answer is a lie even though it cannot be honored.

    The structural half of this is `test_the_runner_has_no_channel_to_receive_an_answer_on`; this
    half is the wording, because an instruction the operator will wait on forever costs the
    session whether or not the runner could have read the reply.
    """
    asking = [
        step.number
        for step in session.STEPS
        if any(promise in step.operator_action for promise in ANSWER_PROMISES)
    ]
    assert asking == []
