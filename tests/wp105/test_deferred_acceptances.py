"""Deferred hardware acceptances + proof the re-verification hook that re-runs them works.

Five things cannot run on this host, because each needs the arm powered and a PG-SAFE-001
PASS that does not exist here: the actual 0xFC torque-ON, the present-pose hold under real
gravity (acceptance ④ physical half), the fitted-motor set as the rig actually answers it,
the power-cycle zero re-verify (⑪, shared with WP-1-02), and the hard-E-Stop drop (⑨⑩
physical half). Each is SKIPPED WITH A REASON — never asserted green — and wired to the
re-verification hook that re-runs the identical judgments the moment a real capture directory
is supplied via `OPENARM_TORQUE_BRINGUP_REAL_FIXTURE` (`02a` §4.1).

The ⑨⑩ facts modelled offline by `backend.torque_bringup.estop` are the design premise, not
evidence. Only the deferred test below reads a measurement, and only when a real capture
exists; a capture that carries no E-Stop observation fails it rather than passing on silence.

The release-to-CAN-stop latency is not among them. This WP produces no such measurement; the
clock constraint is stated in `backend.torque_bringup.stop_latency`.

To prove the hook is real and not a stub, `test_reverify_hook_*` build a synthetic capture in
the same schema a real capture uses and run the hook end to end, including both shapes a
mis-polled bus produces: a pose wider than the ids, and a self-consistent capture that simply
declares an id this rig has no motor on.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.endeffector import GRIPPER_SEND_ID, spatula_build
from backend.torque_bringup import FittedMotorMismatchError
from backend.torque_bringup.reverify import (
    fixture_dir_from_env,
    reverify_from_fixture,
)

_REAL_FIXTURE = fixture_dir_from_env()
_SKIP_REASON = (
    "requires the arm powered, a real CAN adapter, and a PG-SAFE-001 PASS (12 FR-SAF-075, "
    "16 M-2); set OPENARM_TORQUE_BRINGUP_REAL_FIXTURE to a real capture directory to re-verify"
)

# Angle step between adjacent joints in a synthetic captured pose.
_POSE_STEP_RAD = 0.05


def _synthetic_capture(
    within_tolerance: bool = True,
    extra_angle: bool = False,
    declares_absent_motor: bool = False,
) -> dict:
    """One synthetic capture in the real-capture schema.

    Args:
        within_tolerance: The power-cycle zero-residual verdict to embed.
        extra_angle: Whether to record one more angle than the capture declares ids for.
        declares_absent_motor: Whether to declare `0x08` and an angle for it — the shape a
            bus that actually polled the absent motor writes, self-consistent throughout.

    Returns:
        (dict) A capture record.
    """
    send_ids = list(spatula_build().motor_send_ids)
    if declares_absent_motor:
        send_ids.append(GRIPPER_SEND_ID)
    angles = [_POSE_STEP_RAD * index for index in range(len(send_ids))]
    if extra_angle:
        angles.append(_POSE_STEP_RAD * len(send_ids))
    return {
        "host_id": "synthetic-host",
        "engage": {"send_ids": send_ids, "present_pose_rad": angles},
        "zero_residual": {"within_tolerance": within_tolerance},
        "estop": {"can_alive": False, "drop_occurred": True},
    }


def _capture_dir(tmp_path: Path, capture: dict) -> Path:
    (tmp_path / "synthetic-host.json").write_text(json.dumps(capture), encoding="utf-8")
    return tmp_path


# --- Hook mechanism: proves the re-verification plumbing works (synthetic data) ---


def test_reverify_hook_runs_over_a_capture_dir(tmp_path: Path) -> None:
    verifications = reverify_from_fixture(_capture_dir(tmp_path, _synthetic_capture()))
    assert len(verifications) == 1
    verification = verifications[0]
    # A guarded engage holds the present pose: zero commanded displacement.
    assert set(verification.engage_displacement_rad) == {0.0}
    assert verification.engaged_send_ids == spatula_build().motor_send_ids
    assert verification.zero_residual_within_tolerance


def test_reverify_hook_refuses_a_capture_wider_than_the_ids_it_declares(
    tmp_path: Path,
) -> None:
    # A capture that reports more angles than ids is internally broken; the width refusal
    # catches it before any of its numbers are believed.
    capture_dir = _capture_dir(tmp_path, _synthetic_capture(extra_angle=True))
    with pytest.raises(FittedMotorMismatchError):
        reverify_from_fixture(capture_dir)


def test_reverify_hook_refuses_a_capture_that_polled_an_absent_motor(tmp_path: Path) -> None:
    # What a mis-polling bus actually writes: eight ids and eight angles, agreeing with
    # itself. Nothing inside the record contradicts anything else, so the refusal has to
    # come from the fitted profile — motor 0x08 answered 0 of 20 polls on this rig.
    capture_dir = _capture_dir(tmp_path, _synthetic_capture(declares_absent_motor=True))
    with pytest.raises(FittedMotorMismatchError, match="fitted tool carries"):
        reverify_from_fixture(capture_dir)


def test_reverify_hook_rejects_an_empty_capture_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        reverify_from_fixture(tmp_path)


# --- Deferred hardware acceptances: skipped with a reason, re-run only on a real capture ---


@pytest.mark.skipif(_REAL_FIXTURE is None, reason="actual 0xFC torque-ON: " + _SKIP_REASON)
def test_deferred_real_torque_on_engage() -> None:
    assert _REAL_FIXTURE is not None
    for verification in reverify_from_fixture(_REAL_FIXTURE):
        assert verification.engage_displacement_rad, "no real engage in the capture"


@pytest.mark.skipif(
    _REAL_FIXTURE is None, reason="present-pose hold under gravity: " + _SKIP_REASON
)
def test_deferred_present_pose_hold_no_bounce() -> None:
    assert _REAL_FIXTURE is not None
    for verification in reverify_from_fixture(_REAL_FIXTURE):
        # A real engage must still command zero displacement; the physical bounce is
        # bounded by the real hold gains, judged on the real capture.
        assert set(verification.engage_displacement_rad) == {0.0}


@pytest.mark.skipif(_REAL_FIXTURE is None, reason="fitted-motor set on the rig: " + _SKIP_REASON)
def test_deferred_real_engage_addresses_only_fitted_motors() -> None:
    # On the rig the fitted build is the spatula: seven motors and no 0x08. A real capture
    # that names an eighth id is a bus that polled a motor nobody answers on.
    assert _REAL_FIXTURE is not None
    for verification in reverify_from_fixture(_REAL_FIXTURE):
        assert verification.engaged_send_ids == spatula_build().motor_send_ids


@pytest.mark.skipif(_REAL_FIXTURE is None, reason="power-cycle zero re-verify: " + _SKIP_REASON)
def test_deferred_power_cycle_zero_residual() -> None:
    # Acceptance ⑪: shares the WP-1-02 evidence — the power-cycle residual within tolerance.
    assert _REAL_FIXTURE is not None
    for verification in reverify_from_fixture(_REAL_FIXTURE):
        assert verification.zero_residual_within_tolerance


@pytest.mark.skipif(_REAL_FIXTURE is None, reason="hard-E-Stop drop: " + _SKIP_REASON)
def test_deferred_hard_estop_drop() -> None:
    # Acceptance ⑨⑩ physical half. The offline model in `backend.torque_bringup.estop`
    # returns these two as constants because they are the design premise; this is the only
    # place they are read off a measurement. A capture with no E-Stop observation reports
    # the bus alive and no drop, so it fails here instead of passing on an absent key.
    assert _REAL_FIXTURE is not None
    for verification in reverify_from_fixture(_REAL_FIXTURE):
        assert verification.estop_can_alive is False
        assert verification.estop_drop_occurred is True
