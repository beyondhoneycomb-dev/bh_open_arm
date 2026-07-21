"""Deferred acceptances ①②④⑤⑥ (real 16 motors) + proof the hook that re-runs them works.

None of these five can run on this host: they need 16 powered motors with torque OFF
asserted first (`12` FR-SAF-075), and there is no motor, no power, and no vcan here.
So each is SKIPPED WITH A REASON — never asserted green — and each is wired to the
re-verification hook that re-runs the identical judgment the moment a real capture
directory is supplied via `OPENARM_RID_REAL_FIXTURE` (plan 02a §4.1).

To prove the hook itself is real and not a stub, `test_reverify_hook_*` build a
synthetic capture directory in the `dump.py` schema — the same schema a real capture
uses — and run the hook end to end. That exercises the plumbing without pretending
to have reached hardware; the hardware truth stays in the skipped tests above.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.can.rid.evaluate import DumpEvaluation
from backend.can.rid.judge import PgStatus
from backend.can.rid.layout import ARM_MOTOR_TYPES, ARM_SEND_IDS, DM4340_MOTOR_IDS, J7_MOTOR_ID
from backend.can.rid.registers import RID_OC, RID_OT, RID_OV, RID_UV
from backend.can.rid.reverify import fixture_dir_from_env, reverify_from_fixture
from tests.wp0b07 import rid_fixtures as fx

_REAL_FIXTURE = fixture_dir_from_env()
_MARGIN_LSB = 20
_SKIP_REASON = (
    "requires 16 powered motors with torque-OFF asserted first (12 FR-SAF-075); "
    "set OPENARM_RID_REAL_FIXTURE to a real capture directory to re-verify"
)


def _write_arm_capture(directory: Path, iface: str) -> None:
    """Write one arm's 8-motor healthy capture into a dump JSON file.

    Args:
        directory: The capture directory.
        iface: The interface name (also the file stem).
    """
    motors = {
        send_id: fx.healthy_motor(motor_type, timeout_lsb=1000)
        for send_id, motor_type in zip(ARM_SEND_IDS, ARM_MOTOR_TYPES, strict=True)
    }
    (directory / f"{iface}.json").write_text(json.dumps(fx.dump(iface, motors)), encoding="utf-8")


def _synthetic_capture_dir(tmp_path: Path) -> Path:
    """Build a synthetic two-arm (16-motor) capture directory.

    Args:
        tmp_path: The pytest temp directory.

    Returns:
        (Path) The capture directory holding one dump file per arm.
    """
    for iface in ("oa_fl", "oa_fr"):
        _write_arm_capture(tmp_path, iface)
    return tmp_path


# --- Hook mechanism: proves the re-verification plumbing works (synthetic data) ---


def test_reverify_hook_runs_over_a_capture_dir(tmp_path: Path) -> None:
    evaluations = reverify_from_fixture(_synthetic_capture_dir(tmp_path), _MARGIN_LSB)
    assert len(evaluations) == 2
    for evaluation in evaluations:
        assert isinstance(evaluation, DumpEvaluation)
        # Every arm read all 8 motors: no read failure (① shape).
        assert evaluation.rid9.missing_motor_ids == ()
        assert evaluation.rid9.status is PgStatus.PASS
        # J7 classified DM4310 (④ shape).
        assert evaluation.j7 is not None and evaluation.j7.status is PgStatus.PASS
        # DM4340 VMAX classified for both DM4340 joints (⑤ shape).
        assert set(evaluation.vmax) == set(DM4340_MOTOR_IDS)
        # UV/OT/OC/OV recorded for all 8 motors (⑥ shape).
        for motor in evaluation.per_motor:
            assert set(motor.protection) == {RID_UV, RID_OT, RID_OC, RID_OV}


def test_reverify_hook_rejects_an_empty_capture_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        reverify_from_fixture(tmp_path, _MARGIN_LSB)


# --- Deferred hardware acceptances: skipped with a reason, re-run only on a real capture ---


@pytest.mark.skipif(_REAL_FIXTURE is None, reason="① " + _SKIP_REASON)
def test_deferred_all16_rid9_read() -> None:
    assert _REAL_FIXTURE is not None
    for evaluation in reverify_from_fixture(_REAL_FIXTURE, _MARGIN_LSB):
        assert evaluation.rid9.missing_motor_ids == ()


@pytest.mark.skipif(_REAL_FIXTURE is None, reason="② " + _SKIP_REASON)
def test_deferred_rid9_branch_judgment() -> None:
    assert _REAL_FIXTURE is not None
    for evaluation in reverify_from_fixture(_REAL_FIXTURE, _MARGIN_LSB):
        # Each motor lands in exactly one branch — the judgment is total.
        assert all(m.branch is not None for m in evaluation.rid9.per_motor)


@pytest.mark.skipif(_REAL_FIXTURE is None, reason="④ " + _SKIP_REASON)
def test_deferred_j7_tmax_judgment() -> None:
    assert _REAL_FIXTURE is not None
    j7_seen = [e.j7 for e in reverify_from_fixture(_REAL_FIXTURE, _MARGIN_LSB) if e.j7]
    assert j7_seen, f"no J7 (motor 0x{J7_MOTOR_ID:02X}) RID 23 in the capture"


@pytest.mark.skipif(_REAL_FIXTURE is None, reason="⑤ " + _SKIP_REASON)
def test_deferred_dm4340_vmax_judgment() -> None:
    assert _REAL_FIXTURE is not None
    for evaluation in reverify_from_fixture(_REAL_FIXTURE, _MARGIN_LSB):
        assert evaluation.vmax, "no DM4340 VMAX read in the capture"


@pytest.mark.skipif(_REAL_FIXTURE is None, reason="⑥ " + _SKIP_REASON)
def test_deferred_protection_thresholds_recorded() -> None:
    assert _REAL_FIXTURE is not None
    for evaluation in reverify_from_fixture(_REAL_FIXTURE, _MARGIN_LSB):
        for motor in evaluation.per_motor:
            assert motor.protection, f"no UV/OT/OC/OV recorded for motor 0x{motor.motor_id:02X}"
