"""Item ② — an unspecified side blocks startup. RUNS HERE.

An unset `side` leaves LeRobot's ±5° defaults in force and the arm silently does not
move (`01` FR-SYS-013), so it must block torque-ON, not warn.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.can.lock import LockState
from backend.preflight import TorqueOnBlockedError, authorize_torque_on, check_side
from backend.preflight.preflight import JogSessionPreflight
from contracts.plugin.config import Side
from tests.wp2a09.builders import passing_inputs


def test_unspecified_side_blocks() -> None:
    result = check_side(None)
    assert not result.passed
    assert "side unspecified" in result.detail


def test_specified_side_passes() -> None:
    assert check_side(Side.LEFT).passed
    assert check_side(Side.RIGHT).passed


def test_unspecified_side_blocks_torque_end_to_end(self_held_lock_state: LockState) -> None:
    inputs = dataclasses.replace(passing_inputs(self_held_lock_state), side=None)
    report = JogSessionPreflight().run(inputs)
    assert not report.may_enable_torque
    with pytest.raises(TorqueOnBlockedError):
        authorize_torque_on(report)
