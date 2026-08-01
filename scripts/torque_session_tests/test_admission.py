"""The admission gates that decide whether a person is asked to hold a live arm.

Each is checked against ground truth the runner does not own: whether the rig binding resolves
to something callable, which motor ids the fitted tool declares, and what the calibration files
on disk record. A gate that agrees with itself is what this file exists to rule out.
"""

from __future__ import annotations

import importlib.util
from dataclasses import replace
from pathlib import Path

import pytest

import backend.config.store
import backend.endeffector
from backend.endeffector import GRIPPER_SEND_ID, gripper_build, spatula_build
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


def _point_the_rig_at(
    monkeypatch: pytest.MonkeyPatch, module_name: str, attribute_name: str
) -> None:
    """Resolve the rig binding through a stand-in module with a known attribute shape.

    `json` is used because it is guaranteed to import and carries both a callable and a plain
    string at module level. What is under test is what the runner accepts as a write path, not
    anything about JSON.
    """
    monkeypatch.setattr(session, "TORQUE_RIG_MODULE", module_name)
    monkeypatch.setattr(session, "TORQUE_RIG_FACTORY", attribute_name)


def test_a_name_bound_to_a_non_callable_is_not_a_torque_write_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _point_the_rig_at(monkeypatch, "json", "__name__")
    assert session.torque_rig_factory() is None
    result = session.AdmissionResult()
    session._admit_torque_write_path(result, _config(tmp_path))
    assert result.ok is False


def test_a_missing_name_is_not_a_torque_write_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _point_the_rig_at(monkeypatch, "json", "build_engage_bus")
    assert session.torque_rig_factory() is None
    result = session.AdmissionResult()
    session._admit_torque_write_path(result, _config(tmp_path))
    assert result.ok is False


def test_a_name_bound_to_a_callable_is_a_torque_write_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _point_the_rig_at(monkeypatch, "json", "loads")
    assert callable(session.torque_rig_factory())
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


def _calibration_tree(
    tmp_path: Path, power_cycle_verified: bool, rezero_each_session: bool
) -> Path:
    """This bench's real calibration files, copied into `tmp_path` with the two flags replaced.

    Copied rather than synthesized so the vectors, the checksum and the schema generation stay
    whatever the rig actually wrote; only the flags under test differ.
    """
    from backend.calibration.atomic_io import (
        calibration_path_for,
        load_calibration,
        save_calibration_atomic,
    )
    from backend.config.store import default_config_directory

    source = default_config_directory() / session.CALIBRATION_DIRNAME
    directory = tmp_path / session.CALIBRATION_DIRNAME
    directory.mkdir(parents=True, exist_ok=True)
    for robot_id in session.CALIBRATION_ROBOT_IDS.values():
        calibration = load_calibration(calibration_path_for(source, robot_id))
        save_calibration_atomic(
            calibration_path_for(directory, robot_id),
            replace(
                calibration,
                zero_power_cycle_verified=power_cycle_verified,
                require_rezero_each_session=rezero_each_session,
            ),
        )
    return tmp_path


def _admit_calibration_from(monkeypatch: pytest.MonkeyPatch, root: Path) -> session.AdmissionResult:
    """Run the calibration gate against a config directory of our choosing."""
    monkeypatch.setattr(backend.config.store, "default_config_directory", lambda: root)
    result = session.AdmissionResult()
    session._admit_calibration(result, _config(root))
    return result


def test_this_rig_is_admitted_by_the_calibration_gate(tmp_path: Path) -> None:
    result = session.AdmissionResult()
    session._admit_calibration(result, _config(tmp_path))
    assert result.ok is True, result.render()


def test_an_unverified_power_cycle_zero_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _calibration_tree(tmp_path, power_cycle_verified=False, rezero_each_session=True)
    assert _admit_calibration_from(monkeypatch, root).ok is False


def test_turning_off_the_rezero_requirement_does_not_verify_the_power_cycle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _calibration_tree(tmp_path, power_cycle_verified=False, rezero_each_session=False)
    assert _admit_calibration_from(monkeypatch, root).ok is False


def test_a_verified_power_cycle_zero_is_admitted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _calibration_tree(tmp_path, power_cycle_verified=True, rezero_each_session=True)
    assert _admit_calibration_from(monkeypatch, root).ok is True


def test_a_gate_that_raises_is_recorded_as_a_refusal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _explode(_result: object, _config: object) -> None:
        raise RuntimeError("bus went away")

    monkeypatch.setattr(session, "ADMISSION_GATES", (_explode,))
    assert session.admit(_config(tmp_path)).ok is False
