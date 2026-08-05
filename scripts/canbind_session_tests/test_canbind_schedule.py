"""The operator reads the timetable, and only then does the reader detach.

A shell shows a command's output when the command ends. So a tool that forks first and prints
after has printed nothing the operator can act on, and one that prints "move now" while running
has printed it into a screen that will not show it until the moment has passed — the trap that
cost this bench three E-Stop measurements (`05` §1). Both properties are checked here against
the entry point, not against a docstring.
"""

from __future__ import annotations

import io
import subprocess
import time
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import pytest

from backend.endeffector import SIDE_LEFT, SIDE_RIGHT
from scripts import canbind_session as session
from scripts.canbind_session_tests.canbind_doubles import (
    channel_lister,
    lock_manager_factory,
    two_channels,
)

# Far enough ahead that the epoch handed to the fork cannot be confused with the fork's own clock.
DISTANT_START_SECONDS = 3600.0

# The epoch crosses the argv as text with millisecond precision, so it comes back rounded.
EPOCH_TOLERANCE_SECONDS = 0.01

# Ways a Python module can read from whoever ran it. None may appear in the tool: the scheduling
# command has returned by the time the round runs, so a prompt reaches a terminal that is no
# longer showing this program's output.
INPUT_READERS = ("input(", "sys.stdin", "getpass", "fileinput")


def _run_argv(captures: Path) -> list[str]:
    """The argv an operator types to schedule a left-arm round."""
    return [
        "--arm",
        SIDE_LEFT,
        "--captures",
        str(captures),
        "--run",
        session.HOLD_ACKNOWLEDGEMENT_FLAG,
    ]


def test_the_timetable_is_on_the_screen_before_the_reader_detaches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """What the operator has to act on is printed by the command that returns, not by the fork."""
    printed_at_fork: list[str] = []
    buffer = io.StringIO()

    def _record_fork(config: session.SessionConfig, start_epoch: float) -> Path:
        printed_at_fork.append(buffer.getvalue())
        assert config.side == SIDE_LEFT
        assert start_epoch > time.time()
        return tmp_path / session.LOG_FILENAME

    monkeypatch.setattr(session, "list_can_channels", channel_lister(two_channels()))
    monkeypatch.setattr(session, "LockManager", lock_manager_factory(tmp_path))
    monkeypatch.setattr(session, "spawn_worker", _record_fork)

    with redirect_stdout(buffer):
        code = session.main(_run_argv(tmp_path))

    assert code == session.EXIT_OK
    already_shown = printed_at_fork[0]
    assert "채널 열림" in already_shown, "the timetable has to precede the fork"
    assert "기준값 읽음" in already_shown
    assert session.LABEL_BY_SIDE[SIDE_LEFT] in already_shown


def test_every_instant_the_operator_is_shown_is_a_wall_clock_time() -> None:
    """Relative time means nothing to somebody holding an arm and watching a clock."""
    plan = session.plan_round(time.time() + DISTANT_START_SECONDS)

    rendered = session.render_timetable(plan, SIDE_LEFT)

    for epoch in (plan.open_epoch, plan.baseline_epoch, plan.move_end_epoch):
        assert time.strftime(session.WALL_CLOCK_FORMAT, time.localtime(epoch)) in rendered


def test_the_scheduled_round_is_recorded_before_the_verdict_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`--status` between the fork and the verdict has to say "running", not "never started"."""

    def _fork_nothing(config: session.SessionConfig, start_epoch: float) -> Path:
        assert start_epoch > 0.0
        return session.session_dir(config.captures_root) / session.LOG_FILENAME

    monkeypatch.setattr(session, "list_can_channels", channel_lister(two_channels()))
    monkeypatch.setattr(session, "LockManager", lock_manager_factory(tmp_path))
    monkeypatch.setattr(session, "spawn_worker", _fork_nothing)

    with redirect_stdout(io.StringIO()):
        assert session.main(_run_argv(tmp_path)) == session.EXIT_OK
        code = session.report_status(tmp_path)

    assert code == session.EXIT_RUNNING


def _spawned(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, start_epoch: float) -> dict[str, Any]:
    """Run `spawn_worker` with the fork replaced, and return the call it would have made."""
    captured: dict[str, Any] = {}

    def _record(argv: list[str], **kwargs: Any) -> None:
        captured["argv"] = argv
        captured["kwargs"] = kwargs

    monkeypatch.setattr(subprocess, "Popen", _record)
    config = session.SessionConfig(side=SIDE_RIGHT, captures_root=tmp_path)
    session.spawn_worker(config, start_epoch)
    return captured


def test_the_forked_reader_cannot_read_the_operators_terminal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A detached process reading that terminal asks a question nobody will ever see."""
    captured = _spawned(monkeypatch, tmp_path, time.time())

    assert captured["kwargs"]["stdin"] is subprocess.DEVNULL
    assert captured["kwargs"]["start_new_session"] is True


def test_the_forked_reader_runs_the_arm_and_the_instant_the_operator_was_shown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A worker left to read its own clock moves every instant the operator wrote down."""
    start_epoch = time.time() + DISTANT_START_SECONDS

    argv = _spawned(monkeypatch, tmp_path, start_epoch)["argv"]

    assert argv[argv.index("--arm") + 1] == SIDE_RIGHT
    passed = float(argv[argv.index("--start-epoch") + 1])
    assert passed == pytest.approx(start_epoch, abs=EPOCH_TOLERANCE_SECONDS)
    assert "--worker" in argv


def test_the_tool_has_no_channel_to_receive_an_answer_on() -> None:
    """Nothing the operator is told to do may require them to reply.

    The acknowledgement is a flag on the scheduling command for this reason: by the time the
    round runs, the process that would read an answer is detached with its stdin closed.
    """
    source = Path(session.__file__).read_text(encoding="utf-8")

    assert [reader for reader in INPUT_READERS if reader in source] == []
