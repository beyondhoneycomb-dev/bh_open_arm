"""The engage capture is judged against this rig's fitted motor set, not against its own.

The hook's width check compares a capture's pose against the id list the same capture supplied,
so a capture that consistently names an absent motor clears it. These stand the capture next to
`default_profile()` instead, which is the only place the fitted set is a fact rather than an
input. The hook is stubbed: what is under test is the runner's second line, not the hook.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

import backend.torque_bringup.reverify
from backend.endeffector import GRIPPER_SEND_ID, default_profile
from scripts import torque_session as session

FITTED = tuple(default_profile().motor_send_ids)
HELD_IN_PLACE = tuple(0.0 for _ in FITTED)


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


def test_every_capture_in_a_directory_is_judged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    good = StubVerification(FITTED, HELD_IN_PLACE, True)
    unzeroed = StubVerification(FITTED, HELD_IN_PLACE, False)
    _stub_hook(monkeypatch, [good, unzeroed])
    with pytest.raises(session.SessionRefusedError, match="영점"):
        session._stage_torque_bringup(tmp_path)
