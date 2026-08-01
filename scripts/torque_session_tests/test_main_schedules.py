"""What `main()` does after the admission gates have spoken.

This is the boundary the whole runner exists to hold: the admission verdict decides whether a
person is called to a brakeless arm, `--run` decides whether anything is scheduled at all, and
the timetable has to be on the operator's screen before the worker is forked, because a shell
shows a command's output only once the command has ended. None of the three is visible from a
test that stops at `admit()`, so the fork is stubbed and `main()` is driven end to end.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from scripts import torque_session as session

# A selection that reaches the release step, so the timetable is not refused before it is printed.
RELEASING_NUMBERS = (1, 2)
RELEASING_SELECTION = ",".join(str(number) for number in RELEASING_NUMBERS)

# The least lead the operator can be given and still read a timetable, put both hands on the arm
# and settle before the first transition. A lead of zero means the first instant on the timetable
# has already passed by the time the text finishes scrolling.
OPERATOR_LEAD_FLOOR_SECONDS = 10.0

# How far ahead a rendered timetable is placed so that a relative rendering of the same plan
# cannot coincide with the wall-clock rendering of it.
DISTANT_PLAN_SECONDS = 3600.0

# The shortest instruction that can tell a pair of hands what to do with a brakeless 40 Nm arm.
OPERATOR_INSTRUCTION_FLOOR_CHARS = 20

# What `--plan` says in place of a capture directory for a step whose content is an action. The
# line is the operator's only signal that nothing will be written, so it is read literally.
NO_CAPTURE_LINE = "캡처 : 없음 — 이 단계는 측정하지 않는다"


class SpawnRecorder:
    """Stands in for the fork, recording what the runner would have scheduled and when."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.printed_before_fork = ""

    def __call__(
        self, steps: tuple[session.Step, ...], config: session.SessionConfig, start_epoch: float
    ) -> Path:
        """Record the scheduling call and return the log path the real fork would return."""
        self.calls.append({"steps": steps, "config": config, "start_epoch": start_epoch})
        return session.session_dir(config.captures_root) / session.LOG_FILENAME


def _admission(passed: bool) -> session.AdmissionResult:
    """An admission result of the given verdict, carrying a mix of lines either way."""
    result = session.AdmissionResult()
    result.record(True, "장착 엔드이펙터", "fixed_spatula")
    result.record(passed, "토크 쓰기 경로", "stubbed")
    return result


def _stub_admission(monkeypatch: pytest.MonkeyPatch, passed: bool) -> SpawnRecorder:
    """Fix the admission verdict and replace the fork, leaving the rest of `main()` real."""
    recorder = SpawnRecorder()
    monkeypatch.setattr(session, "admit", lambda _config: _admission(passed))
    monkeypatch.setattr(session, "spawn_worker", recorder)
    return recorder


def _run_args(tmp_path: Path, *extra: str) -> list[str]:
    """The argument vector of a scheduling command confined to a temporary capture tree."""
    return ["--captures", str(tmp_path), "--steps", RELEASING_SELECTION, *extra]


def _releasing_steps() -> tuple[session.Step, ...]:
    """The steps `RELEASING_SELECTION` names, in session order."""
    selected = tuple(step for step in session.STEPS if step.number in set(RELEASING_NUMBERS))
    assert len(selected) == len(RELEASING_NUMBERS), RELEASING_SELECTION
    return selected


def test_a_refused_admission_schedules_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A refused gate has to stop `--run`, not merely be printed above it."""
    recorder = _stub_admission(monkeypatch, passed=False)
    code = session.main(_run_args(tmp_path, "--run"))
    assert code == session.EXIT_REFUSED
    assert recorder.calls == []


def test_a_refused_admission_says_so_and_names_the_refusing_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_admission(monkeypatch, passed=False)
    session.main(_run_args(tmp_path, "--run"))
    printed = capsys.readouterr().out
    assert "[거부] 토크 쓰기 경로" in printed


def test_a_passing_admission_alone_schedules_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Without `--run` the command is a precondition check, and a check schedules no session."""
    recorder = _stub_admission(monkeypatch, passed=True)
    code = session.main(_run_args(tmp_path))
    assert code == session.EXIT_OK
    assert recorder.calls == []


def test_the_run_flag_schedules_exactly_the_selected_steps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = _stub_admission(monkeypatch, passed=True)
    code = session.main(_run_args(tmp_path, "--run"))
    assert code == session.EXIT_OK
    assert len(recorder.calls) == 1
    scheduled = [step.number for step in recorder.calls[0]["steps"]]
    assert scheduled == list(RELEASING_NUMBERS)


def test_the_timetable_reaches_the_operator_before_the_worker_is_forked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Three E-Stop measurements were lost to instructions printed while the command still ran.

    The output of a bash command appears when the command ends, so an instruction printed after
    the fork is invisible until the measurement it was meant to prepare for is over. What is
    asserted here is the order of the two side effects, not that both happened.
    """
    recorder = _stub_admission(monkeypatch, passed=True)

    def _record_then_schedule(
        steps: tuple[session.Step, ...], config: session.SessionConfig, start_epoch: float
    ) -> Path:
        recorder.printed_before_fork = capsys.readouterr().out
        return SpawnRecorder.__call__(recorder, steps, config, start_epoch)

    monkeypatch.setattr(session, "spawn_worker", _record_then_schedule)
    assert session.main(_run_args(tmp_path, "--run")) == session.EXIT_OK

    already_seen = recorder.printed_before_fork
    assert recorder.calls[0]["steps"] != ()
    for step in recorder.calls[0]["steps"]:
        assert step.title in already_seen
        assert step.operator_action in already_seen
    first_instant = session._wall_clock(recorder.calls[0]["start_epoch"])
    assert first_instant in already_seen


def test_the_first_step_is_scheduled_a_lead_ahead_of_the_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The lead is the whole safety of a scheduled design: the arm has no brake to buy time."""
    recorder = _stub_admission(monkeypatch, passed=True)
    before = time.time()
    assert session.main(_run_args(tmp_path, "--run")) == session.EXIT_OK
    lead = recorder.calls[0]["start_epoch"] - before
    assert lead >= OPERATOR_LEAD_FLOOR_SECONDS


def test_the_timetable_is_wall_clock_and_names_every_torque_transition() -> None:
    """Relative time is useless to somebody holding an arm and watching a clock."""
    plan = session.schedule(_releasing_steps(), time.time() + DISTANT_PLAN_SECONDS)
    rendered = session.render_timetable(plan)
    for step, epoch in plan:
        assert session._wall_clock(epoch) in rendered
        assert session._wall_clock(epoch + step.duration_seconds) in rendered
        assert f"토크: {step.torque.value}" in rendered
        assert step.operator_action in rendered
        assert step.software_action in rendered


def test_the_plan_names_every_torque_transition(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--plan` is what an operator reads before deciding to schedule anything."""
    code = session.main(["--plan", "--captures", str(tmp_path), "--steps", RELEASING_SELECTION])
    assert code == session.EXIT_OK
    printed = capsys.readouterr().out
    for step in _releasing_steps():
        assert f"토크 : {step.torque.value}" in printed
        assert step.operator_action in printed


def test_the_plan_says_which_steps_write_a_capture_and_which_write_none(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A step whose content is an action has no capture and no hook, and has to say so.

    Printing a hook command for a step that has none hands the operator a pytest invocation over
    a path that is the literal word None, and printing a capture directory for it promises a file
    that never appears.
    """
    code = session.main(["--plan", "--captures", str(tmp_path), "--steps", RELEASING_SELECTION])
    assert code == session.EXIT_OK
    printed = capsys.readouterr().out
    measuring = [step for step in _releasing_steps() if step.measures]
    silent = [step for step in _releasing_steps() if not step.measures]
    assert measuring != []
    assert silent != []
    for step in measuring:
        assert f"<captures>/{step.capture_dirname}/" in printed
        assert f"{step.hook_env_var}=<dir> pytest {step.hook_test_path}" in printed
    assert printed.count(NO_CAPTURE_LINE) == len(silent)
    assert "None" not in printed


@pytest.mark.parametrize("step", session.STEPS, ids=lambda step: step.key)
def test_every_step_tells_the_hands_on_the_arm_what_to_do(step: session.Step) -> None:
    """A step with no operator action is a scheduled instant nobody was told to prepare for."""
    assert step.operator_action.strip() != ""
    if step.torque is not session.Torque.NONE:
        assert len(step.operator_action.strip()) >= OPERATOR_INSTRUCTION_FLOOR_CHARS


@pytest.mark.parametrize("step", session.STEPS, ids=lambda step: step.key)
def test_every_step_declares_exactly_one_of_a_measurement_and_an_action(
    step: session.Step,
) -> None:
    """A step with neither is an instant the operator was called to for nothing.

    A step with both is worse: `run_step` dispatches to the action and the capture the timetable
    promised is never written, silently.
    """
    assert (step.produce is None) is not (step.perform is None)
    assert step.measures is (step.produce is not None)


@pytest.mark.parametrize("step", session.STEPS, ids=lambda step: step.key)
def test_a_measuring_step_carries_the_hook_that_judges_its_capture(step: session.Step) -> None:
    """The capture directory, the hook variable and the hook path travel together or not at all.

    A capture written where no hook reads it is a file that is never judged, and a hook pointed
    at a step that writes nothing fails on an empty directory.
    """
    carried = (step.capture_dirname, step.hook_env_var, step.hook_test_path, step.stage)
    if step.measures:
        assert all(field is not None for field in carried)
    else:
        assert all(field is None for field in carried)


def test_no_selection_means_the_whole_session() -> None:
    assert session._selected_steps(None) == session.STEPS


def test_an_unknown_step_number_is_refused() -> None:
    unknown = max(session.STEP_BY_NUMBER) + 1
    with pytest.raises(SystemExit, match=str(unknown)):
        session._selected_steps(str(unknown))


def test_an_unknown_step_number_beside_a_known_one_is_refused() -> None:
    """Silently dropping the number nobody recognizes runs a session nobody asked for."""
    unknown = max(session.STEP_BY_NUMBER) + 1
    with pytest.raises(SystemExit, match=str(unknown)):
        session._selected_steps(f"1,{unknown}")


def test_an_empty_selection_is_not_the_whole_session() -> None:
    """`--steps ''` asked for nothing, and the whole table starts with an engage."""
    assert session._selected_steps("") == ()
