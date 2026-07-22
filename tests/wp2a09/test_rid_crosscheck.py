"""Item ① — a RID 21/22/23 mismatch blocks the MIT torque send. RUNS HERE.

The live sixteen-motor read is hardware-deferred (see test_deferred_rid_reverify), but
the torque *gate* over a read runs here on synthetic evaluations: a matching read
passes, any mismatch blocks, an unread motor blocks fail-closed, and — end to end — a
mismatched read makes `authorize_torque_on` raise, so no MIT frame is authorized.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.can.lock import LockState
from backend.can.rid.registers import RID_TMAX
from backend.preflight import (
    RidCrosscheck,
    TorqueOnBlockedError,
    authorize_torque_on,
    check_rid_crosscheck,
)
from backend.preflight.preflight import JogSessionPreflight
from tests.wp2a09.builders import build_rid_evaluation, passing_inputs

_DM4340_JOINT = 0x03
_J7 = 0x07


def test_matching_read_passes() -> None:
    result = check_rid_crosscheck(RidCrosscheck.confirmed(build_rid_evaluation()))
    assert result.passed


def test_tmax_mismatch_blocks() -> None:
    evaluation = build_rid_evaluation(
        break_motor=_DM4340_JOINT, break_rid=RID_TMAX, break_value=5.0
    )
    result = check_rid_crosscheck(RidCrosscheck.confirmed(evaluation))
    assert not result.passed
    assert "0x03" in result.detail


def test_j7_misregistration_blocks() -> None:
    # J7's TMAX read back as 5 Nm (DM3507) instead of 10 Nm (DM4310): both the limit
    # comparison and the PG-J7-001 judgment must block.
    evaluation = build_rid_evaluation(break_motor=_J7, break_rid=RID_TMAX, break_value=5.0)
    result = check_rid_crosscheck(RidCrosscheck.confirmed(evaluation))
    assert not result.passed
    assert "PG-J7-001" in result.detail


def test_partial_read_blocks() -> None:
    # A motor whose RID 9 was not read is a partial read; PG-RID-001 forbids torque-ON.
    evaluation = build_rid_evaluation(drop_timeout_on=_DM4340_JOINT)
    result = check_rid_crosscheck(RidCrosscheck.confirmed(evaluation))
    assert not result.passed
    assert "PG-RID-001" in result.detail


def test_unavailable_read_blocks_fail_closed() -> None:
    result = check_rid_crosscheck(RidCrosscheck.unavailable("no motors on this host"))
    assert not result.passed


def test_mismatch_blocks_torque_end_to_end(self_held_lock_state: LockState) -> None:
    mismatched = RidCrosscheck.confirmed(
        build_rid_evaluation(break_motor=_DM4340_JOINT, break_rid=RID_TMAX, break_value=5.0)
    )
    inputs = dataclasses.replace(passing_inputs(self_held_lock_state), rid=mismatched)
    report = JogSessionPreflight().run(inputs)
    assert not report.may_enable_torque
    with pytest.raises(TorqueOnBlockedError):
        authorize_torque_on(report)
