"""Item ⑤ — an unselected or invalid clamp canon refuses torque. RUNS HERE.

The canonical clamp limit set (`12` FR-SAF-045) is what torque-ON runs inside. None
selected refuses torque; a selected-but-invalid set (operational wider than mechanical)
refuses just the same, reusing `SafetyLimits.validate`.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.can.lock import LockState
from backend.preflight import TorqueOnBlockedError, authorize_torque_on, check_clamp_canon
from backend.preflight.preflight import JogSessionPreflight
from tests.wp2a09.builders import invalid_clamp_canon, passing_inputs, valid_clamp_canon


def test_unselected_canon_blocks() -> None:
    result = check_clamp_canon(None)
    assert not result.passed
    assert "unselected" in result.detail


def test_invalid_canon_blocks() -> None:
    result = check_clamp_canon(invalid_clamp_canon())
    assert not result.passed
    assert "invalid" in result.detail


def test_valid_canon_passes() -> None:
    assert check_clamp_canon(valid_clamp_canon()).passed


def test_unselected_canon_blocks_torque_end_to_end(self_held_lock_state: LockState) -> None:
    inputs = dataclasses.replace(passing_inputs(self_held_lock_state), clamp_canon=None)
    report = JogSessionPreflight().run(inputs)
    assert not report.may_enable_torque
    with pytest.raises(TorqueOnBlockedError):
        authorize_torque_on(report)
