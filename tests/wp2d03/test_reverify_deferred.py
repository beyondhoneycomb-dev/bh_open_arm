"""The deferred real-registration acceptance: SKIP-with-reason plus a real re-verification hook.

Phase 2 (real Freedrive registration) needs a PG-FRIC-001 hardware pass and torque-ON, neither of
which exists here, so that acceptance is skipped with a reason — never asserted green (THE ONE
RULE). What is proved is that the hook exists and re-runs the identical entry decision the moment
real captures are supplied, and that it reports evidence carrying its hardware preconditions
rather than manufacturing a pass.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("mujoco")

from backend.freedrive import FRICTION_PASSED_STATUS, fixture_dir_from_env
from backend.freedrive.reverify import reverify_freedrive_registration
from backend.friction.constants import PG_FRIC_001_STATUS_DEFERRED
from tests.wp2d03._support import (
    ENTRY_POSE_RAD,
    ENTRY_VELOCITY_RAD_S,
    arm_safety_limits,
    friction_seed,
    gravity_backend,
)


def _write_capture(directory: Path, name: str, friction_status: str) -> None:
    (directory / name).write_text(
        json.dumps(
            {
                "q": list(ENTRY_POSE_RAD),
                "dq": list(ENTRY_VELOCITY_RAD_S),
                "friction_status": friction_status,
            }
        ),
        encoding="utf-8",
    )


def test_real_registration_is_deferred_when_no_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENARM_FREEDRIVE_REAL_FIXTURE", raising=False)
    if fixture_dir_from_env() is None:
        pytest.skip(
            "Freedrive real registration deferred: needs PG-FRIC-001 PASS + torque-ON on "
            "hardware; re-run with OPENARM_FREEDRIVE_REAL_FIXTURE set to real captures."
        )
    raise AssertionError("a real fixture was present; this host is expected to defer")


def test_hook_reruns_entry_on_a_passed_capture(tmp_path: Path) -> None:
    _write_capture(tmp_path, "session_a.json", FRICTION_PASSED_STATUS)
    evidence = reverify_freedrive_registration(
        tmp_path, gravity_backend(), friction_seed(), arm_safety_limits()
    )
    assert len(evidence) == 1
    record = evidence[0]
    assert record.path_c_offered is True
    assert record.effort_saturated is False
    assert record.engaged is True
    assert record.min_hold_kd > 0.0
    # Evidence, never a pass: the hardware preconditions are carried, not evaluated away.
    assert "torque-ON" in record.torque_on_precondition
    assert "PG-FRIC-001" in record.friction_pass_precondition


def test_hook_respects_a_not_passed_capture(tmp_path: Path) -> None:
    _write_capture(tmp_path, "session_b.json", PG_FRIC_001_STATUS_DEFERRED)
    record = reverify_freedrive_registration(
        tmp_path, gravity_backend(), friction_seed(), arm_safety_limits()
    )[0]
    assert record.path_c_offered is False
    assert record.engaged is False


def test_hook_raises_on_an_empty_fixture(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        reverify_freedrive_registration(
            tmp_path, gravity_backend(), friction_seed(), arm_safety_limits()
        )
