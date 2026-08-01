"""`--check` is the runner judging its own refusals, so its cases must be able to fail.

Two one-line edits used to leave it fully green while the session would schedule an engage on a
brakeless arm: dropping the write-path gate from `ADMISSION_GATES`, and making
`_require_torque_write_path` return unconditionally. Each is performed here, and the self-check
has to notice.

The case list itself is written out rather than counted off the report, because a report compared
against its own length stays green when seven of eight cases are deleted.
"""

from __future__ import annotations

import pytest

from scripts import torque_session as session

# Every case `_check_refusals` is expected to reach a verdict on. A case that stops running is a
# refusal nobody proved fires, and this runner's history is that a refusal nobody proved is a
# refusal that had already been neutered.
REFUSAL_CASES = (
    "refuse/synthetic-into-capture-tree",
    "refuse/stop-latency-key",
    "refuse/absent-motor-pose",
    "refuse/privilege-escalation",
    "refuse/shell-wrapped-escalation",
    "gate/torque-write-path",
    "refuse/torque-write-path",
    "refuse/unreleased-selection",
)


def _refusal_report() -> list[tuple[bool, str]]:
    """Run the refusal half of the self-check and return its lines."""
    report: list[tuple[bool, str]] = []
    session._check_refusals(report)
    return report


def _failed_labels(report: list[tuple[bool, str]]) -> list[str]:
    """The lines the self-check judged as failures."""
    return [line for passed, line in report if not passed]


def _carries_nothing(_node: object, _key: str) -> bool:
    """A payload scan that finds nothing, standing in for a neutered one."""
    return False


def _measuring_steps() -> tuple[session.Step, ...]:
    """The steps that write a capture, and so the ones with a layout to judge."""
    return tuple(step for step in session.STEPS if step.measures)


@pytest.mark.usefixtures("no_process_execution")
def test_the_self_check_passes_on_this_host() -> None:
    assert session.run_self_check() == session.EXIT_OK


@pytest.mark.usefixtures("no_process_execution")
def test_the_self_check_exit_code_goes_non_zero_when_a_case_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`torque_session.sh` documents this exit code as the verdict, so it has to be able to fail."""

    def _report_a_failure(report: list[tuple[bool, str]]) -> None:
        report.append((False, "layout/engage: the hook refused the layout"))

    monkeypatch.setattr(session, "_check_layouts", _report_a_failure)
    assert session.run_self_check() == session.EXIT_REFUSED


def test_a_layout_the_hook_refuses_is_reported_as_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every layout is still reported, and every one of them as the failure it was."""

    def _refuse(_step: object, _measurement: object) -> None:
        raise session.SessionRefusedError("the hook would not load this layout")

    monkeypatch.setattr(session, "stage_capture", _refuse)
    report: list[tuple[bool, str]] = []
    session._check_layouts(report)
    measuring = _measuring_steps()
    assert measuring != ()
    assert len(report) == len(measuring)
    assert [passed for passed, _ in report] == [False] * len(measuring)
    for step in measuring:
        assert any(f"layout/{step.key}" in line for _, line in report), step.key


def test_a_step_that_measures_nothing_gets_no_layout_verdict() -> None:
    """A step with no payload has no layout, so `--check` may neither pass nor fail it.

    A "layout OK" line for a step that writes nothing is a pass nobody earned, and the other
    outcome is worse: handed no staging callable, the check reports a failure the operator cannot
    close, and `--check` goes red on a runner that is behaving correctly.
    """
    report: list[tuple[bool, str]] = []
    session._check_layouts(report)
    judged = [line for _, line in report]
    silent = [step for step in session.STEPS if not step.measures]
    assert silent != []
    for step in session.STEPS:
        named = any(f"layout/{step.key}" in line for line in judged)
        assert named is step.measures, step.key


@pytest.mark.usefixtures("no_process_execution")
def test_every_refusal_case_reports_a_verdict() -> None:
    report = _refusal_report()
    assert _failed_labels(report) == []
    reported = [line for _, line in report]
    for case in REFUSAL_CASES:
        assert any(line.startswith(case) for line in reported), case
    assert len(report) == len(REFUSAL_CASES)


@pytest.mark.usefixtures("no_process_execution")
def test_dropping_the_write_path_gate_fails_the_self_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remaining = tuple(
        gate for gate in session.ADMISSION_GATES if gate is not session._admit_torque_write_path
    )
    monkeypatch.setattr(session, "ADMISSION_GATES", remaining)
    failed = _failed_labels(_refusal_report())
    assert any("gate/torque-write-path" in line for line in failed), failed


@pytest.mark.usefixtures("no_process_execution")
def test_neutering_the_write_path_refusal_fails_the_self_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if session.torque_rig_factory() is not None:
        pytest.skip("the rig binding exists, so refusing is no longer the correct verdict")

    def _admit_anything(_step_key: str) -> None:
        return

    monkeypatch.setattr(session, "_require_torque_write_path", _admit_anything)
    failed = _failed_labels(_refusal_report())
    assert any("refuse/torque-write-path" in line for line in failed), failed


@pytest.mark.usefixtures("no_process_execution")
def test_neutering_the_stop_latency_refusal_fails_the_self_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session, "_payload_carries_key", _carries_nothing)
    failed = _failed_labels(_refusal_report())
    assert any("refuse/stop-latency-key" in line for line in failed), failed


@pytest.mark.usefixtures("no_process_execution")
def test_neutering_the_unreleased_selection_refusal_fails_the_self_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _admit_anything(_steps: object) -> None:
        return

    monkeypatch.setattr(session, "assert_session_releases_torque", _admit_anything)
    failed = _failed_labels(_refusal_report())
    assert any("refuse/unreleased-selection" in line for line in failed), failed
