"""`run_step` on a session whose two steps have different content.

One step measures and one acts. The measuring step's verdict is a capture its own hook agreed to;
the acting step's verdict is the line the action returned. A step declaring neither is a scheduled
instant the operator was called to a brakeless arm for and nothing to do with them, so it refuses
rather than passing quietly.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import torque_session as session

ENGAGE_STEP = 1
RELEASE_STEP = 2

# What a performer that reached a motor would hand back to be recorded.
PERFORMED_LINE = "0x01..0x07 토크 해제 확인"


def _config(tmp_path: Path) -> session.SessionConfig:
    """A session config confined to a temporary tree."""
    return session.SessionConfig(
        arm=session.ARM_LEFT,
        captures_root=tmp_path,
        rid_capture_dir=tmp_path / "rid",
        operator="test",
        candump_path=None,
    )


def _release() -> session.Step:
    """The step whose content is the torque coming back down."""
    return session.STEP_BY_NUMBER[RELEASE_STEP]


def _perform_successfully(_config: session.SessionConfig) -> str:
    """Stand in for an action that reached the motors."""
    return PERFORMED_LINE


def _measure_successfully(_config: session.SessionConfig) -> session.Measurement:
    """Stand in for an engage that measured, handing back the layout the hook accepts."""
    synthetic = session._synthetic_torque_bringup()
    return session.Measurement(
        source=session.SOURCE_MEASURED, name=synthetic.name, payload=synthetic.payload
    )


def test_the_release_step_acts_and_measures_nothing() -> None:
    """The content of this step is a person taking the arm's weight, and no number comes of it."""
    release = _release()
    assert release.torque is session.Torque.RELEASE
    assert release.measures is False
    assert release.perform is not None


def test_the_release_step_refuses_while_the_torque_write_path_is_unassembled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recording a drop that never reached a motor ends a session green on an energized arm.

    The writer is cleared rather than left to whatever this host happens to present. With a
    writer bound, this step's own code opens both channels and sends 0xFD to the fitted motors —
    a real release on a brakeless arm nobody is holding — and what would stop it here is only
    that the CAN binding record happens to resolve nothing on the machine running the suite.
    """
    monkeypatch.setattr(session, "BIMANUAL_CAN_WRITER", None)
    passed, detail = session.run_step(_release(), _config(tmp_path))
    assert passed is False
    assert "토크 쓰기 경로" in detail
    assert detail.startswith(f"{_release().key}:")


def test_a_performer_that_returns_a_line_has_that_line_recorded(tmp_path: Path) -> None:
    """The action's own account of what it did is the verdict, not a sentence composed here."""
    acting = replace(_release(), perform=_perform_successfully)
    passed, detail = session.run_step(acting, _config(tmp_path))
    assert passed is True
    assert detail == PERFORMED_LINE


def test_a_performer_that_refuses_is_not_recorded_as_a_pass(tmp_path: Path) -> None:
    """A refusal raised inside the action has to become this step's verdict, not escape it."""

    def _refuse(_config: session.SessionConfig) -> str:
        raise session.SessionRefusedError("the bus went away mid-release")

    acting = replace(_release(), perform=_refuse)
    passed, detail = session.run_step(acting, _config(tmp_path))
    assert passed is False
    assert "the bus went away mid-release" in detail


def test_a_performer_that_raises_something_else_is_not_recorded_as_a_pass(tmp_path: Path) -> None:
    """Any failure of the action is this step's verdict; one failed step keeps the session going."""

    def _explode(_config: session.SessionConfig) -> str:
        raise RuntimeError("the socket closed")

    acting = replace(_release(), perform=_explode)
    passed, detail = session.run_step(acting, _config(tmp_path))
    assert passed is False
    assert "the socket closed" in detail


def test_a_step_declaring_neither_a_measurement_nor_an_action_is_refused(tmp_path: Path) -> None:
    """The dispatch has no third branch, and falling off the end must not read as a pass."""
    hollow = replace(_release(), produce=None, perform=None)
    passed, detail = session.run_step(hollow, _config(tmp_path))
    assert passed is False
    assert hollow.key in detail


def test_a_measuring_step_writes_its_capture_and_names_the_hook_that_judged_it(
    tmp_path: Path,
) -> None:
    """The measuring branch is the one that reaches the capture tree, and it says where."""
    engage = replace(session.STEP_BY_NUMBER[ENGAGE_STEP], produce=_measure_successfully)
    assert engage.capture_dirname is not None
    assert engage.hook_test_path is not None
    passed, detail = session.run_step(engage, _config(tmp_path))
    assert passed is True, detail
    written = tmp_path / engage.capture_dirname
    files = sorted(written.glob("*.json"))
    assert [path.name for path in files] == ["layout-check.json"]
    assert json.loads(files[0].read_text(encoding="utf-8"))["engage"]["send_ids"] != []
    assert engage.hook_test_path in detail


def test_a_step_whose_action_ran_records_no_capture(tmp_path: Path) -> None:
    """Nothing is written for a step that measures nothing, whatever its action returned."""
    acting = replace(_release(), perform=_perform_successfully)
    session.run_step(acting, _config(tmp_path))
    assert list(tmp_path.rglob("*.json")) == []


def test_a_payload_with_nowhere_to_be_written_is_refused(tmp_path: Path) -> None:
    """A payload from a step that declares no capture directory is a payload nobody expects.

    The step still carries its hook, so the refusal here can only come from the missing
    directory. Without that check the path arithmetic raises instead, and a `TypeError` is not a
    verdict the operator can read or the state file can record as a refusal.
    """
    homeless = replace(session.STEP_BY_NUMBER[ENGAGE_STEP], capture_dirname=None)
    assert homeless.stage is not None
    with pytest.raises(session.SessionRefusedError, match=homeless.key):
        session.write_capture(homeless, _measure_successfully(_config(tmp_path)), tmp_path)
    assert list(tmp_path.rglob("*.json")) == []


def test_a_payload_with_no_hook_to_judge_it_is_refused(tmp_path: Path) -> None:
    """The hook judging before the write is the whole ordering; a step with no hook has no judge.

    The refusal has to say the step brought no hook. Calling the absent hook and catching what
    comes back blames the hook for refusing a payload it never saw, and every other refusal in
    `stage_capture` reads as that same sentence — so the wrapped exception type is what tells the
    two apart.
    """
    unjudged = replace(session.STEP_BY_NUMBER[ENGAGE_STEP], stage=None)
    with pytest.raises(session.SessionRefusedError) as refusal:
        session.write_capture(unjudged, _measure_successfully(_config(tmp_path)), tmp_path)
    message = str(refusal.value)
    assert unjudged.key in message
    assert TypeError.__name__ not in message
    assert list(tmp_path.rglob("*.json")) == []
