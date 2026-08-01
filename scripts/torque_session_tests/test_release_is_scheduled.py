"""No timetable may end with the arm energized.

`Torque.RELEASE` exists on one step. A selection that stops before it engages a brakeless arm
and then stops talking, and no `finally` can repair that — dropping torque on an unsupported arm
is a fall, so the release has to be an instant the operator was shown. The only enforceable form
of that is refusing the selection, and the refusal has to sit in front of every entry point:
the operator's command, and the detached worker that is spawned with whatever it was given.

`Torque.HOLD` is counted as energizing and no step of this session carries it, so the holds here
are built rather than selected. A selection whose every step holds is one that ends with the arm
held up by whatever engaged it, and with no instant scheduled to put it down; a rule that reads
only the engage sees the same selection as a session that ends at rest.
"""

from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import torque_session as session

# The two steps of the session, by the number `--steps` names them with.
ENGAGE_STEP = 1
RELEASE_STEP = 2

# Enough schedule slip to put a step behind its instant without exceeding the worker's
# tolerance, so the loop runs every step immediately instead of sleeping through the session.
RAN_LATE_SECONDS = 100.0

# Past the tolerance: every step of a two-step selection is late enough to be given up on.
GAVE_UP_SECONDS = 400.0

# Step numbers the synthetic holds take. Above the real table so a table carrying both the real
# steps and the holds has no number twice, and `--steps` can name a hold without naming a step
# that exists.
HOLD_NUMBERS = (3, 4, 5, 6)

# Selections whose every step holds a torque somebody else turned on.
HOLD_ONLY_SELECTIONS = (*((number,) for number in HOLD_NUMBERS), HOLD_NUMBERS)

# Titles that tell the two synthetic steps apart from the real ones in a refusal message, so a
# refusal naming the wrong step is visible rather than indistinguishable.
HOLD_TITLE = "합성 유지 단계 — 토크는 이미 켜져 있다"
INERT_TITLE = "합성 무동작 단계 — 토크를 건드리지 않는다"

# Number for the step that changes nothing, appended after a real one.
INERT_NUMBER = 99


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
    """The steps those numbers select, in session order.

    Every number asked for has to resolve. A selection that quietly comes back shorter than it
    was named — or empty — leaves the property under test with nothing to bite on, and a
    renumbered table would turn every case in this file green without anybody reading it.
    """
    selected = tuple(step for step in session.STEPS if step.number in set(numbers))
    assert len(selected) == len(set(numbers)), f"{numbers} does not resolve against this table"
    return selected


def _hold(number: int) -> session.Step:
    """A step that holds a torque an earlier step turned on.

    The runner treats a hold as energizing because a hold presumes an engage the operator was
    never shown an instant for. Nothing in the table carries `Torque.HOLD`, so the only way to
    keep that judgment under test is to build the step.
    """
    return replace(
        session.STEP_BY_NUMBER[ENGAGE_STEP],
        number=number,
        key=f"hold-{number}",
        title=HOLD_TITLE,
        torque=session.Torque.HOLD,
    )


def _holds(*numbers: int) -> tuple[session.Step, ...]:
    """One synthetic hold per number, in the order given."""
    return tuple(_hold(number) for number in numbers)


def _inert_tail() -> session.Step:
    """A step that commands no torque transition, appended after a real one.

    No step in the table carries `Torque.NONE` either, which is exactly why the refusal has to be
    judged over the whole selection: a tail that changes nothing would otherwise be read as a
    selection that ends with the torque down.
    """
    return replace(
        session.STEP_BY_NUMBER[RELEASE_STEP],
        number=INERT_NUMBER,
        key="inert",
        title=INERT_TITLE,
        torque=session.Torque.NONE,
        perform=None,
    )


def _table_with_holds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a step table carrying the real steps and one synthetic hold per hold number.

    `main()` resolves `--steps` against the module's table, so a hold selection can only reach
    the command's own refusal through a table that has a hold in it.
    """
    table = (*session.STEPS, *_holds(*HOLD_NUMBERS))
    monkeypatch.setattr(session, "STEPS", table)
    monkeypatch.setattr(session, "STEP_BY_NUMBER", {step.number: step for step in table})


def test_a_selection_ending_on_an_engage_is_refused() -> None:
    with pytest.raises(session.SessionRefusedError, match="토크가 켜진 채로 끝난다"):
        session.assert_session_releases_torque(_steps(ENGAGE_STEP))


def test_a_selection_ending_on_a_hold_is_refused() -> None:
    with pytest.raises(session.SessionRefusedError, match="토크가 켜진 채로 끝난다"):
        session.assert_session_releases_torque((*_steps(ENGAGE_STEP), *_holds(HOLD_NUMBERS[0])))


def test_a_hold_after_the_release_puts_the_torque_back_up() -> None:
    """A hold is not a neutral tail: it presumes an engage, so it re-arms a released selection."""
    with pytest.raises(session.SessionRefusedError, match="토크가 켜진 채로 끝난다"):
        session.assert_session_releases_torque(
            (*_steps(ENGAGE_STEP, RELEASE_STEP), *_holds(HOLD_NUMBERS[0]))
        )


@pytest.mark.parametrize("numbers", HOLD_ONLY_SELECTIONS)
def test_a_selection_of_holds_alone_is_refused(numbers: tuple[int, ...]) -> None:
    """A hold with no engage in front of it is judged live, and no engage was ever shown.

    Selected without the engage, none of these steps turns the torque on, so a rule that only
    counts the engage reads every one of them as a session that ends with the arm at rest. It
    ends with the arm energized by whatever engaged it, and with no instant scheduled to put it
    down.
    """
    with pytest.raises(session.SessionRefusedError, match="토크가 켜진 채로 끝난다"):
        session.assert_session_releases_torque(_holds(*numbers))


@pytest.mark.parametrize("numbers", HOLD_ONLY_SELECTIONS)
def test_a_hold_alone_leaves_the_arm_energized(numbers: tuple[int, ...]) -> None:
    assert session.torque_is_live_after(_holds(*numbers)) is True


@pytest.mark.parametrize("numbers", HOLD_ONLY_SELECTIONS)
def test_the_command_refuses_to_print_a_timetable_of_holds_alone(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    numbers: tuple[int, ...],
) -> None:
    _table_with_holds(monkeypatch)
    selection = ",".join(str(number) for number in numbers)
    code = session.main(["--plan", "--steps", selection, "--captures", str(tmp_path)])
    assert code == session.EXIT_REFUSED
    assert "토크가 켜진 채로 끝난다" in capsys.readouterr().out


def test_a_hold_between_the_engage_and_the_release_is_admitted() -> None:
    """A hold in the middle is fine; what is refused is a hold with nothing after it."""
    engage, release = _steps(ENGAGE_STEP, RELEASE_STEP)
    session.assert_session_releases_torque((engage, *_holds(HOLD_NUMBERS[0]), release))


def test_the_whole_session_is_admitted() -> None:
    session.assert_session_releases_torque(session.STEPS)


def test_the_release_step_alone_is_admitted() -> None:
    session.assert_session_releases_torque(_steps(RELEASE_STEP))


def test_an_inert_step_after_an_engage_does_not_count_as_a_release() -> None:
    with pytest.raises(session.SessionRefusedError, match="토크가 켜진 채로 끝난다"):
        session.assert_session_releases_torque((*_steps(ENGAGE_STEP), _inert_tail()))


def test_an_inert_step_after_the_release_is_admitted() -> None:
    session.assert_session_releases_torque((*_steps(ENGAGE_STEP, RELEASE_STEP), _inert_tail()))


def test_an_engage_after_the_release_is_refused() -> None:
    reengaged = (*_steps(ENGAGE_STEP, RELEASE_STEP), session.STEP_BY_NUMBER[ENGAGE_STEP])
    with pytest.raises(session.SessionRefusedError, match="토크가 켜진 채로 끝난다"):
        session.assert_session_releases_torque(reengaged)


def test_the_refusal_names_the_step_that_left_the_torque_up() -> None:
    with pytest.raises(session.SessionRefusedError) as refusal:
        session.assert_session_releases_torque((*_steps(ENGAGE_STEP), _inert_tail()))
    assert session.STEP_BY_NUMBER[ENGAGE_STEP].title in str(refusal.value)


def test_the_refusal_names_a_trailing_hold_as_the_step_that_left_the_torque_up() -> None:
    """The last step to raise the torque is the hold, not the engage two steps before it.

    Naming the engage sends the operator to the wrong instant on the timetable, and it is the
    symptom of a rule that stopped counting holds as energizing at all.
    """
    with pytest.raises(session.SessionRefusedError) as refusal:
        session.assert_session_releases_torque((*_steps(ENGAGE_STEP), *_holds(HOLD_NUMBERS[0])))
    assert HOLD_TITLE in str(refusal.value)


def test_the_command_refuses_to_print_a_timetable_that_leaves_torque_on(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = session.main(["--plan", "--step", str(ENGAGE_STEP), "--captures", str(tmp_path)])
    assert code == session.EXIT_REFUSED
    assert "토크가 켜진 채로 끝난다" in capsys.readouterr().out


def test_the_command_still_prints_a_timetable_that_releases(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    selection = f"{ENGAGE_STEP},{RELEASE_STEP}"
    code = session.main(["--plan", "--steps", selection, "--captures", str(tmp_path)])
    assert code == session.EXIT_OK
    assert session.STEP_BY_NUMBER[RELEASE_STEP].title in capsys.readouterr().out


def test_the_worker_refuses_a_selection_that_leaves_torque_on(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _admit_everything(monkeypatch)
    with pytest.raises(session.SessionRefusedError, match="토크가 켜진 채로 끝난다"):
        session.run_worker(_steps(ENGAGE_STEP), _config(tmp_path), time.time())


def test_a_session_that_engaged_and_never_released_records_that_torque_may_be_live(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _admit_everything(monkeypatch)
    start = time.time() - RAN_LATE_SECONDS
    session.run_worker(_steps(ENGAGE_STEP, RELEASE_STEP), _config(tmp_path), start)
    recorded = _recorded(tmp_path)
    assert session.TORQUE_STATE_KEY in recorded
    assert recorded[session.TORQUE_STATE_KEY]["passed"] is False


def test_a_session_that_never_engaged_records_no_live_torque(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _admit_everything(monkeypatch)
    start = time.time() - RAN_LATE_SECONDS
    session.run_worker(_steps(RELEASE_STEP), _config(tmp_path), start)
    assert session.TORQUE_STATE_KEY not in _recorded(tmp_path)


def _skip_sentence() -> str:
    """The part of the skip verdict that carries no substituted value.

    Derived from the runner's own constant rather than retyped, and taken after the last
    placeholder so it is the longest collision-free part of the sentence. A search for the skip
    verb alone matches `_require_torque_write_path`'s refusal, which uses the same word about
    something else entirely — so half of this test used to pass on a step that was never skipped.
    """
    return session.SCHEDULE_SLIP_SKIP_DETAIL.rsplit("}", maxsplit=1)[-1]


def test_the_skip_sentence_belongs_to_the_skip_verdict_alone() -> None:
    """The slip tests below read a skip by this sentence, so no other refusal may contain it.

    The skip verb on its own occurs in the torque-write-path refusal too, about something else
    entirely, and matching that word alone is how half of `test_schedule_slip_never_skips_the_
    release_step` used to pass on a step that was never skipped. A second occurrence of the
    longer form anywhere in the runner puts it back in that state.
    """
    source = Path(session.__file__).read_text(encoding="utf-8")
    assert source.count(_skip_sentence()) == 1


def test_schedule_slip_never_skips_the_release_step(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _admit_everything(monkeypatch)
    start = time.time() - GAVE_UP_SECONDS
    session.run_worker(_steps(ENGAGE_STEP, RELEASE_STEP), _config(tmp_path), start)
    recorded = _recorded(tmp_path)
    overslept = str(recorded[session.STEP_BY_NUMBER[ENGAGE_STEP].key]["detail"])
    released = str(recorded[session.STEP_BY_NUMBER[RELEASE_STEP].key]["detail"])
    assert _skip_sentence() in overslept
    assert session._wall_clock(start) in overslept
    assert _skip_sentence() not in released


def test_a_step_inside_the_slip_tolerance_is_not_skipped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Late but still watched: the operator is standing there, so the step runs and is judged."""
    _admit_everything(monkeypatch)
    start = time.time() - RAN_LATE_SECONDS
    session.run_worker(_steps(ENGAGE_STEP, RELEASE_STEP), _config(tmp_path), start)
    recorded = _recorded(tmp_path)
    detail = str(recorded[session.STEP_BY_NUMBER[ENGAGE_STEP].key]["detail"])
    assert _skip_sentence() not in detail


def test_the_worker_stops_when_its_own_re_admission_refuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The operator's shell returned long ago; the rig may have changed since it did.

    Nothing else re-checks between scheduling and the first frame, so a lock somebody else took
    in that window has to stop the session here rather than be discovered mid-engage.
    """

    def _refuse(_config: object) -> session.AdmissionResult:
        result = session.AdmissionResult()
        result.record(True, "test", "still fine")
        result.record(False, "CAN 바인딩", "somebody else holds the writer lock")
        return result

    monkeypatch.setattr(session, "admit", _refuse)
    code = session.run_worker(
        _steps(ENGAGE_STEP, RELEASE_STEP), _config(tmp_path), time.time() - RAN_LATE_SECONDS
    )
    assert code == session.EXIT_REFUSED
    recorded = _recorded(tmp_path)
    assert "admission" in recorded
    assert session.STEP_BY_NUMBER[ENGAGE_STEP].key not in recorded
    assert session.STEP_BY_NUMBER[RELEASE_STEP].key not in recorded


def test_the_worker_exit_code_reports_a_refused_step(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`--status` is the verdict, and it is read as an exit code by whatever ran the session."""
    _admit_everything(monkeypatch)
    code = session.run_worker(
        _steps(RELEASE_STEP), _config(tmp_path), time.time() - RAN_LATE_SECONDS
    )
    assert code == session.EXIT_REFUSED
    assert _recorded(tmp_path)[session.STEP_BY_NUMBER[RELEASE_STEP].key]["passed"] is False


def test_the_worker_exit_code_is_green_only_when_every_step_passed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _admit_everything(monkeypatch)

    def _pass(_step: object, _config: object) -> tuple[bool, str]:
        return True, "stubbed pass"

    monkeypatch.setattr(session, "run_step", _pass)
    code = session.run_worker(
        _steps(RELEASE_STEP), _config(tmp_path), time.time() - RAN_LATE_SECONDS
    )
    assert code == session.EXIT_OK


def test_consecutive_steps_are_spaced_by_the_operators_changeover_gap() -> None:
    """The gap is the operator changing grip and the previous motion damping out."""
    assert session.STEP_GAP_SECONDS > 0
    plan = session.schedule(_steps(ENGAGE_STEP, RELEASE_STEP), time.time())
    first_step, first_epoch = plan[0]
    _, second_epoch = plan[1]
    expected = first_step.duration_seconds + session.STEP_GAP_SECONDS
    assert second_epoch - first_epoch == pytest.approx(expected)


def test_status_shows_the_operator_that_torque_may_still_be_live(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _admit_everything(monkeypatch)
    start = time.time() - RAN_LATE_SECONDS
    session.run_worker(_steps(ENGAGE_STEP, RELEASE_STEP), _config(tmp_path), start)
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
        session.run_worker(_steps(ENGAGE_STEP, RELEASE_STEP), _config(tmp_path), start)
    assert session.TORQUE_STATE_KEY in _recorded(tmp_path)
