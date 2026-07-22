"""Acceptance ⑧/⑩ and CTR-CAL@v1 shape: atomic disk SoT, gripper capture, integrity.

⑧ is proven two ways: a deterministic crash injection (a write that dies between the
temp file and the rename leaves the previous file wholly intact), and a SIGKILL stress
(100 kills mid-write, the target is never a corrupt JSON). ⑩ is the gripper endpoint
capture and its `captured` flag surviving a reload.
"""

from __future__ import annotations

import json
import os
import random
import signal
from pathlib import Path

import jsonschema
import pytest

from backend.calibration import atomic_io
from backend.calibration.atomic_io import (
    calibration_path_for,
    load_calibration,
    save_calibration_atomic,
)
from backend.calibration.schema import (
    MOTOR_COUNT,
    CalibrationError,
    OpenArmCalibration,
    ZeroMethod,
)

_SIGKILL_ITERATIONS = 100


def _sample_calibration() -> OpenArmCalibration:
    """Return a minimal valid calibration for persistence tests."""
    return OpenArmCalibration(
        robot_type="oa_openarm_follower",
        robot_id="persist",
        side="left",
        motor_zero_raw=[0.0] * MOTOR_COUNT,
        urdf_zero_offset=[0.0] * MOTOR_COUNT,
        gripper_open_rad=0.0,
        gripper_close_rad=-0.7,
        zero_method=ZeroMethod.HARDSTOP_BUMP,
    )


def test_roundtrip_matches_frozen_schema(tmp_path: Path) -> None:
    """A saved calibration validates against schema.json and reloads identically."""
    path = tmp_path / "arm.oa_cal.json"
    written = save_calibration_atomic(path, _sample_calibration())
    reloaded = load_calibration(path)
    assert reloaded.motor_zero_raw == written.motor_zero_raw
    assert reloaded.zero_method is ZeroMethod.HARDSTOP_BUMP
    assert reloaded.require_rezero_each_session is True  # conservative default (⑦)
    # The on-disk bytes satisfy the frozen JSON Schema.
    schema = json.loads((Path(atomic_io.__file__).parent / "schema.json").read_text("utf-8"))
    jsonschema.validate(json.loads(path.read_text("utf-8")), schema)


def test_checksum_tamper_is_rejected(tmp_path: Path) -> None:
    """A body edited without updating the checksum fails to load."""
    path = tmp_path / "arm.oa_cal.json"
    save_calibration_atomic(path, _sample_calibration())
    data = json.loads(path.read_text("utf-8"))
    data["gripper_open_rad"] = 9.99  # tamper, leave checksum stale
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CalibrationError):
        load_calibration(path)


def test_gripper_endpoints_persist_with_captured_flag(make_follower) -> None:
    """Captured gripper endpoints and their `captured` flag survive a reload (⑩)."""
    follower, _bus = make_follower()
    follower.connect_readonly()
    follower.set_zero(ZeroMethod.HARDSTOP_BUMP, rest_confirmed=True)
    # Fresh from set_zero the flags are off (0xFE re-zeroed the gripper too).
    assert follower.calibration_model.gripper_open_captured is False
    follower.capture_gripper_endpoint("open", 0.05)
    follower.capture_gripper_endpoint("close", -0.72)
    reloaded = load_calibration(calibration_path_for(follower.calibration_dir, follower.id))
    assert reloaded.gripper_open_captured is True
    assert reloaded.gripper_close_captured is True
    assert reloaded.gripper_open_rad == pytest.approx(0.05)
    assert reloaded.gripper_close_rad == pytest.approx(-0.72)


def test_crash_between_temp_and_rename_preserves_old_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A write that dies after the temp file but before the rename leaves the old file whole."""
    path = tmp_path / "arm.oa_cal.json"
    original = save_calibration_atomic(path, _sample_calibration())
    original_bytes = path.read_bytes()

    def _boom(_src: object, _dst: object) -> None:
        raise OSError("simulated crash before rename")

    monkeypatch.setattr(atomic_io.os, "replace", _boom)
    changed = OpenArmCalibration(**{**_sample_calibration().__dict__, "gripper_open_rad": 1.23})
    with pytest.raises(OSError):
        save_calibration_atomic(path, changed)
    # The target still holds the whole previous file — never a partial write.
    assert path.read_bytes() == original_bytes
    assert load_calibration(path).gripper_open_rad == original.gripper_open_rad


@pytest.mark.skipif(not hasattr(os, "fork"), reason="fork-based SIGKILL stress needs POSIX fork")
def test_atomic_write_survives_sigkill_stress(tmp_path: Path) -> None:
    """100 SIGKILLs mid-write leave the calibration file never corrupt (⑧).

    Each iteration forks a child that rewrites the file in a tight loop and kills it
    with SIGKILL after a random sub-tick. `os.replace` is POSIX-atomic, so the target
    is always either the whole previous file or the whole next one — `load_calibration`
    (which re-checks the checksum) must never raise on it.
    """
    path = tmp_path / "arm.oa_cal.json"
    save_calibration_atomic(path, _sample_calibration())  # seed a valid file

    for iteration in range(_SIGKILL_ITERATIONS):
        pid = os.fork()
        if pid == 0:  # child: rewrite forever until killed
            try:
                calibration = _sample_calibration()
                while True:
                    calibration.gripper_open_rad = random.random()
                    calibration.created_at = None
                    save_calibration_atomic(path, calibration)
            finally:
                os._exit(0)
        os.sched_yield()
        # Kill somewhere in the write window; a valid target must survive regardless.
        _busy_wait(random.uniform(0.0, 0.003))
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        if path.exists():
            calibration = load_calibration(path)  # raises on any torn/corrupt write
            assert len(calibration.motor_zero_raw) == MOTOR_COUNT, f"iteration {iteration}"


def _busy_wait(seconds: float) -> None:
    """Spin for `seconds` without importing a sleep the child might inherit oddly."""
    import time

    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        pass
