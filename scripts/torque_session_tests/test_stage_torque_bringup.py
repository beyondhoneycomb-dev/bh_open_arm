"""`_stage_torque_bringup` judging the verdicts the WP-1-05 hook hands it.

The hook is stubbed here so that what is exercised is the runner's own line and nothing else:
the fitted-motor comparison against `default_profile()`, the hold-at-present displacement, and
the zero residual.

Only two of those three can refuse a real capture. The hook derives the displacement by
rebuilding the hold from the pose the capture supplied, so it reports 0.0 whatever was really
commanded, and the stub is the only way that branch is ever entered.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

import backend.torque_bringup.reverify
from backend.endeffector import GRIPPER_SEND_ID, default_profile
from scripts import torque_session as session

FITTED = tuple(default_profile().motor_send_ids)
HELD_IN_PLACE = tuple(0.0 for _ in FITTED)

# Joint spacing for a pose that is plainly not the zero pose, so a displacement of 0.0 against
# it is the hook's arithmetic rather than an accident of the numbers chosen.
ARBITRARY_ANGLE_RAD = 0.37


@dataclass(frozen=True)
class StubVerification:
    """The fields `_stage_torque_bringup` reads off one capture's verdict."""

    engaged_send_ids: tuple[int, ...]
    engage_displacement_rad: tuple[float, ...]
    zero_residual_within_tolerance: bool


def _stub_hook(monkeypatch: pytest.MonkeyPatch, verifications: Sequence[StubVerification]) -> None:
    """Make the WP-1-05 hook return the given verdicts for any directory."""

    def _reverify(_fixture_dir: Path) -> list[StubVerification]:
        return list(verifications)

    monkeypatch.setattr(backend.torque_bringup.reverify, "reverify_from_fixture", _reverify)


def test_a_capture_addressing_the_fitted_set_is_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_hook(monkeypatch, [StubVerification(FITTED, HELD_IN_PLACE, True)])
    session._stage_torque_bringup(tmp_path)


def test_a_capture_addressing_an_unfitted_motor_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wider = (*FITTED, GRIPPER_SEND_ID)
    _stub_hook(monkeypatch, [StubVerification(wider, (*HELD_IN_PLACE, 0.0), True)])
    with pytest.raises(session.SessionRefusedError, match="ERROR-PASSIVE"):
        session._stage_torque_bringup(tmp_path)


def test_a_capture_missing_a_fitted_motor_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    narrower = FITTED[:-1]
    _stub_hook(monkeypatch, [StubVerification(narrower, HELD_IN_PLACE[:-1], True)])
    with pytest.raises(session.SessionRefusedError, match="ERROR-PASSIVE"):
        session._stage_torque_bringup(tmp_path)


def test_an_engage_that_moved_the_arm_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    moved = (0.0, *HELD_IN_PLACE[1:-1], 0.02)
    _stub_hook(monkeypatch, [StubVerification(FITTED, moved, True)])
    with pytest.raises(session.SessionRefusedError, match="현재 자세"):
        session._stage_torque_bringup(tmp_path)


def test_a_capture_taken_on_an_unzeroed_arm_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_hook(monkeypatch, [StubVerification(FITTED, HELD_IN_PLACE, False)])
    with pytest.raises(session.SessionRefusedError, match="영점"):
        session._stage_torque_bringup(tmp_path)


def test_the_real_hook_reports_no_displacement_whatever_the_pose(tmp_path: Path) -> None:
    """The unstubbed hook reports 0.0 for every joint of any capture, so that branch is inert.

    `_verify_engage` rebuilds the hold from `present_pose_rad` and subtracts that same pose, and
    the capture format records no commanded target to compare against instead. When this fails
    the hook has started carrying what was really sent: the displacement branch in
    `_stage_torque_bringup` is live from that point and its inert comment is no longer true.
    """
    payload = {
        "host_id": "h",
        "engage": {
            "send_ids": list(FITTED),
            "present_pose_rad": [ARBITRARY_ANGLE_RAD * index for index in range(len(FITTED))],
        },
        "zero_residual": {"within_tolerance": True},
    }
    (tmp_path / "capture.json").write_text(json.dumps(payload), encoding="utf-8")
    verification = backend.torque_bringup.reverify.reverify_from_fixture(tmp_path)[0]
    assert set(verification.engage_displacement_rad) == {0.0}


def test_every_capture_in_a_directory_is_judged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    good = StubVerification(FITTED, HELD_IN_PLACE, True)
    unzeroed = StubVerification(FITTED, HELD_IN_PLACE, False)
    _stub_hook(monkeypatch, [good, unzeroed])
    with pytest.raises(session.SessionRefusedError, match="영점"):
        session._stage_torque_bringup(tmp_path)
