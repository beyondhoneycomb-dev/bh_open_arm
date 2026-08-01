"""No timetable may end with the arm energized.

`Torque.RELEASE` exists on one step. A selection that stops before it engages a brakeless arm
and then stops talking, and no `finally` can repair that — dropping torque on an unsupported arm
is a fall, so the release has to be an instant the operator was shown. The only enforceable form
of that is refusing the selection, and the refusal has to sit in front of every entry point:
the operator's command, and the detached worker that is spawned with whatever it was given.
"""

from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import torque_session as session

# Enough schedule slip to put a step behind its instant without exceeding the worker's
# tolerance, so the loop runs every step immediately instead of sleeping through the session.
RAN_LATE_SECONDS = 100.0

# Past the tolerance: every step of a two-step selection is late enough to be given up on.
GAVE_UP_SECONDS = 400.0


def _config(tmp_path: Path) -> session.SessionConfig:
    """A session config confined to a temporary tree."""
    return session.SessionConfig(
        arm=session.ARM_LEFT,
        captures_root=tmp_path,
        rid_capture_dir=tmp_path / "rid",
        operator="test",
        candump_path=None,
    )


def _admit_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let the worker past its own re-admission without touching a CAN channel."""

    def _admit(_config: object) -> object:
        result = session.AdmissionResult()
        result.record(True, "test", "admission stubbed")
        return result

    monkeypatch.setattr(session, "admit", _admit)


def _recorded(tmp_path: Path) -> dict[str, dict[str, object]]:
    """The worker's state file, as steps keyed by their step key."""
    path = session.session_dir(tmp_path) / session.STATE_FILENAME
    document = json.loads(path.read_text(encoding="utf-8"))
    steps: dict[str, dict[str, object]] = document["steps"]
    return steps


def _steps(*numbers: int) -> tuple[session.Step, ...]:
    """The steps those numbers select, in session order."""
    return tuple(step for step in session.STEPS if step.number in set(numbers))


def _inert_tail() -> session.Step:
    """A step that commands no torque transition, appended after a real one.

    No step in the table carries `Torque.NONE` today, which is exactly why the refusal has to
    be judged over the whole selection: a tail that changes nothing would otherwise be read as
    a selection that ends with the torque down.
    """
    return replace(session.STEP_BY_NUMBER[5], number=99, key="inert", torque=session.Torque.NONE)


def test_a_selection_ending_on_an_engage_is_refused() -> None:
    with pytest.raises(session.SessionRefusedError, match="토크가 켜진 채로 끝난다"):
        session.assert_session_releases_torque(_steps(1))


def test_a_selection_ending_on_a_hold_is_refused() -> None:
    with pytest.raises(session.SessionRefusedError, match="토크가 켜진 채로 끝난다"):
        session.assert_session_releases_torque(_steps(1, 3))


def test_a_selection_reaching_the_release_step_is_admitted() -> None:
    session.assert_session_releases_torque(_steps(1, 3, 6))


def test_the_whole_session_is_admitted() -> None:
    session.assert_session_releases_torque(session.STEPS)


def test_the_release_step_alone_is_admitted() -> None:
    session.assert_session_releases_torque(_steps(6))


def test_an_inert_step_after_an_engage_does_not_count_as_a_release() -> None:
    with pytest.raises(session.SessionRefusedError, match="토크가 켜진 채로 끝난다"):
        session.assert_session_releases_torque((*_steps(1), _inert_tail()))


def test_an_inert_step_after_the_release_is_admitted() -> None:
    session.assert_session_releases_torque((*_steps(1, 6), _inert_tail()))


def test_an_engage_after_the_release_is_refused() -> None:
    reengaged = (*_steps(1, 6), session.STEP_BY_NUMBER[1])
    with pytest.raises(session.SessionRefusedError, match="토크가 켜진 채로 끝난다"):
        session.assert_session_releases_torque(reengaged)


def test_the_refusal_names_the_step_that_left_the_torque_up() -> None:
    with pytest.raises(session.SessionRefusedError) as refusal:
        session.assert_session_releases_torque((*_steps(1), _inert_tail()))
    assert session.STEP_BY_NUMBER[1].title in str(refusal.value)


def test_the_command_refuses_to_print_a_timetable_that_leaves_torque_on(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = session.main(["--plan", "--step", "1", "--captures", str(tmp_path)])
    assert code == session.EXIT_REFUSED
    assert "토크가 켜진 채로 끝난다" in capsys.readouterr().out


def test_the_command_still_prints_a_timetable_that_releases(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = session.main(["--plan", "--steps", "1,6", "--captures", str(tmp_path)])
    assert code == session.EXIT_OK
    assert session.STEP_BY_NUMBER[6].title in capsys.readouterr().out


def test_the_worker_refuses_a_selection_that_leaves_torque_on(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _admit_everything(monkeypatch)
    with pytest.raises(session.SessionRefusedError, match="토크가 켜진 채로 끝난다"):
        session.run_worker(_steps(1), _config(tmp_path), time.time())


def test_a_session_that_engaged_and_never_released_records_that_torque_may_be_live(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _admit_everything(monkeypatch)
    start = time.time() - RAN_LATE_SECONDS
    session.run_worker(_steps(1, 6), _config(tmp_path), start)
    recorded = _recorded(tmp_path)
    assert session.TORQUE_STATE_KEY in recorded
    assert recorded[session.TORQUE_STATE_KEY]["passed"] is False


def test_a_session_that_never_engaged_records_no_live_torque(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _admit_everything(monkeypatch)
    start = time.time() - RAN_LATE_SECONDS
    session.run_worker(_steps(6), _config(tmp_path), start)
    assert session.TORQUE_STATE_KEY not in _recorded(tmp_path)


def test_schedule_slip_never_skips_the_release_step(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _admit_everything(monkeypatch)
    start = time.time() - GAVE_UP_SECONDS
    session.run_worker(_steps(1, 6), _config(tmp_path), start)
    recorded = _recorded(tmp_path)
    assert "건너뛴다" in str(recorded[session.STEP_BY_NUMBER[1].key]["detail"])
    assert "건너뛴다" not in str(recorded[session.STEP_BY_NUMBER[6].key]["detail"])


def test_status_shows_the_operator_that_torque_may_still_be_live(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _admit_everything(monkeypatch)
    start = time.time() - RAN_LATE_SECONDS
    session.run_worker(_steps(1, 6), _config(tmp_path), start)
    capsys.readouterr()
    assert session.report_status(_config(tmp_path)) == session.EXIT_REFUSED
    printed = capsys.readouterr().out
    assert session.TORQUE_STATE_KEY in printed
    assert "팔이 아직 인게이지돼 있을 수 있다" in printed


def test_a_session_whose_producer_raised_still_records_the_live_torque(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _admit_everything(monkeypatch)

    def _explode(_step: object, _config: object) -> tuple[bool, str]:
        raise KeyboardInterrupt

    monkeypatch.setattr(session, "run_step", _explode)
    start = time.time() - RAN_LATE_SECONDS
    with pytest.raises(KeyboardInterrupt):
        session.run_worker(_steps(1, 6), _config(tmp_path), start)
    assert session.TORQUE_STATE_KEY in _recorded(tmp_path)
