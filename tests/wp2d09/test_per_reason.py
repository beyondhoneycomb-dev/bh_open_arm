"""Acceptance ② — the check outcome is shown per reason (RUNS HERE).

A refusal is not a bare boolean: the report attributes each failure to a named reason —
WP-2A-03's ``mechanical_limit`` / ``operational_limit`` for a limit violation, WP-2D-01's
``no_solution_found`` for an unreachable pose — with the joint and bound that failed.
``by_reason`` groups the messages so a UI renders one list per reason.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("openarm_control")
pytest.importorskip("lerobot")

from backend.cartesian_jog import JogStopReason, ReferenceFrame, TcpSelection
from backend.jogclamp import JogClampReason
from backend.moveto import JointMoveTo, NumericMoveTo, PoseMoveTo

_MECHANICAL_OVERSHOOT_RAD = 10.0
_UNREACHABLE_X_OFFSET_M = 3.0


def _home_right_joints(gate: NumericMoveTo) -> tuple[float, ...]:
    return tuple(gate.jog.arm_joints("right").tolist())


def test_mechanical_violation_names_the_joint_and_reason(gate: NumericMoveTo) -> None:
    bad = (_MECHANICAL_OVERSHOOT_RAD,) + _home_right_joints(gate)[1:]

    report = gate.check(JointMoveTo(side="right", joints_rad=bad))

    assert len(report.limit_findings) == 1
    finding = report.limit_findings[0]
    assert finding.reason is JogClampReason.MECHANICAL_LIMIT
    assert finding.side == "right"
    assert finding.joint_number == 1
    assert finding.slot == 0
    assert JogClampReason.MECHANICAL_LIMIT.value in report.by_reason()


def test_operational_violation_is_distinct_from_mechanical(
    tight_operational_gate: NumericMoveTo,
) -> None:
    report = tight_operational_gate.check(
        JointMoveTo(side="right", joints_rad=_home_right_joints(tight_operational_gate))
    )

    reasons = {f.reason for f in report.limit_findings}
    assert reasons == {JogClampReason.OPERATIONAL_LIMIT}
    joint4 = next(f for f in report.limit_findings if f.joint_number == 4)
    assert joint4.upper_deg == pytest.approx(45.0)


def test_no_solution_is_reported_with_its_ik_reason(gate: NumericMoveTo) -> None:
    pose = gate.jog.current_pose("right", ReferenceFrame.WORLD, TcpSelection.FLANGE).copy()
    pose[0] += _UNREACHABLE_X_OFFSET_M

    report = gate.check(PoseMoveTo(side="right", target_pose=tuple(pose.tolist())))

    assert report.ik_finding is not None
    assert report.ik_finding.reason is JogStopReason.NO_SOLUTION
    assert JogStopReason.NO_SOLUTION.value in report.by_reason()


def test_multiple_joint_violations_each_appear(gate: NumericMoveTo) -> None:
    bad = (_MECHANICAL_OVERSHOOT_RAD, _MECHANICAL_OVERSHOOT_RAD) + _home_right_joints(gate)[2:]

    report = gate.check(JointMoveTo(side="right", joints_rad=bad))

    assert len(report.limit_findings) == 2
    assert {f.joint_number for f in report.limit_findings} == {1, 2}
    assert len(report.by_reason()[JogClampReason.MECHANICAL_LIMIT.value]) == 2


def test_passing_check_reports_no_reasons(gate: NumericMoveTo) -> None:
    report = gate.check(JointMoveTo(side="right", joints_rad=_home_right_joints(gate)))

    assert report.passed is True
    assert report.by_reason() == {}
