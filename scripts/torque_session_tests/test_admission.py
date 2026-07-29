"""The admission gates that decide whether a person is asked to hold a live arm.

Two of them are checked here against ground truth the runner does not own: whether the rig
binding module actually exists, and which motor ids the fitted tool declares. A gate that
agrees with itself is what this file exists to rule out.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

import backend.endeffector
from backend.endeffector import GRIPPER_SEND_ID, gripper_build, spatula_build
from scripts import torque_session as session


def _config(tmp_path: Path) -> object:
    """A session config confined to a temporary tree."""
    return session.SessionConfig(
        arm=session.ARM_LEFT,
        captures_root=tmp_path,
        rid_capture_dir=tmp_path / "rid",
        operator="test",
        candump_path=None,
    )


def _rig_binding_exists() -> bool:
    """Whether the torque rig binding is present, probed without the runner's own helper."""
    if importlib.util.find_spec(session.TORQUE_RIG_MODULE) is None:
        return False
    module = importlib.import_module(session.TORQUE_RIG_MODULE)
    return hasattr(module, session.TORQUE_RIG_FACTORY)


def test_torque_write_path_gate_is_installed() -> None:
    assert session._admit_torque_write_path in session.ADMISSION_GATES


def test_torque_write_path_gate_refuses_while_the_rig_binding_is_absent(tmp_path: Path) -> None:
    if _rig_binding_exists():
        pytest.skip(f"{session.TORQUE_RIG_MODULE}.{session.TORQUE_RIG_FACTORY} now exists")
    result = session.AdmissionResult()
    session._admit_torque_write_path(result, _config(tmp_path))
    assert result.ok is False
    assert session.TORQUE_RIG_FACTORY in result.render()


def test_torque_write_path_gate_admits_once_the_rig_binding_exists(tmp_path: Path) -> None:
    if not _rig_binding_exists():
        pytest.skip(f"{session.TORQUE_RIG_MODULE}.{session.TORQUE_RIG_FACTORY} does not exist yet")
    result = session.AdmissionResult()
    session._admit_torque_write_path(result, _config(tmp_path))
    assert result.ok is True


def test_end_effector_gate_refuses_a_profile_that_polls_the_gripper_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(backend.endeffector, "default_profile", gripper_build)
    result = session.AdmissionResult()
    session._admit_end_effector(result, _config(tmp_path))
    assert result.ok is False
    assert f"{GRIPPER_SEND_ID:#04x}" in result.render()


def test_end_effector_gate_admits_the_build_with_no_motor_on_the_gripper_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(backend.endeffector, "default_profile", spatula_build)
    result = session.AdmissionResult()
    session._admit_end_effector(result, _config(tmp_path))
    assert result.ok is True


def test_this_rig_is_admitted_by_the_end_effector_gate(tmp_path: Path) -> None:
    result = session.AdmissionResult()
    session._admit_end_effector(result, _config(tmp_path))
    assert result.ok is True, result.render()


def test_a_gate_that_raises_is_recorded_as_a_refusal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _explode(_result: object, _config: object) -> None:
        raise RuntimeError("bus went away")

    monkeypatch.setattr(session, "ADMISSION_GATES", (_explode,))
    assert session.admit(_config(tmp_path)).ok is False
