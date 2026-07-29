"""`--check` is the runner judging its own refusals, so its cases must be able to fail.

Two one-line edits used to leave it fully green while the session would schedule an engage on a
brakeless arm: dropping the write-path gate from `ADMISSION_GATES`, and making
`_require_torque_write_path` return unconditionally. Each is performed here, and the self-check
has to notice.
"""

from __future__ import annotations

import pytest

from scripts import torque_session as session


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


def test_the_self_check_passes_on_this_host() -> None:
    assert session.run_self_check() == session.EXIT_OK


def test_every_refusal_case_reports_a_verdict() -> None:
    report = _refusal_report()
    assert _failed_labels(report) == []
    assert len(report) >= 1


def test_dropping_the_write_path_gate_fails_the_self_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remaining = tuple(
        gate for gate in session.ADMISSION_GATES if gate is not session._admit_torque_write_path
    )
    monkeypatch.setattr(session, "ADMISSION_GATES", remaining)
    failed = _failed_labels(_refusal_report())
    assert any("gate/torque-write-path" in line for line in failed), failed


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


def test_neutering_the_stop_latency_refusal_fails_the_self_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session, "_payload_carries_key", _carries_nothing)
    failed = _failed_labels(_refusal_report())
    assert any("refuse/stop-latency-key" in line for line in failed), failed


def test_neutering_the_unreleased_selection_refusal_fails_the_self_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _admit_anything(_steps: object) -> None:
        return

    monkeypatch.setattr(session, "assert_session_releases_torque", _admit_anything)
    failed = _failed_labels(_refusal_report())
    assert any("refuse/unreleased-selection" in line for line in failed), failed
