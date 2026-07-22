"""Acceptance ① — an input that fails the checks does not execute (RUNS HERE).

A refused Move-to leaves the committed arm state exactly as it was, for every failure
category: a joint target outside the mechanical envelope, a joint target outside the
tighter operational band, and an EE pose with no IK solution. A passing target, by
contrast, commits. The gate never moves the arm on a failed check.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("openarm_control")
pytest.importorskip("lerobot")

from backend.cartesian_jog import ReferenceFrame, TcpSelection
from backend.moveto import JointMoveTo, NumericMoveTo, PoseMoveTo

_MECHANICAL_OVERSHOOT_RAD = 10.0
_UNREACHABLE_X_OFFSET_M = 3.0
_REACHABLE_Z_OFFSET_M = 0.03


def _home_right_joints(gate: NumericMoveTo) -> tuple[float, ...]:
    return tuple(gate.jog.arm_joints("right").tolist())


def _reachable_pose(gate: NumericMoveTo) -> tuple[float, ...]:
    pose = gate.jog.current_pose("right", ReferenceFrame.WORLD, TcpSelection.FLANGE).copy()
    pose[2] += _REACHABLE_Z_OFFSET_M
    return tuple(pose.tolist())


def test_joint_target_beyond_mechanical_does_not_execute(gate: NumericMoveTo) -> None:
    bad = (_MECHANICAL_OVERSHOOT_RAD,) + _home_right_joints(gate)[1:]
    before = gate.jog.committed_solution()

    result = gate.execute(JointMoveTo(side="right", joints_rad=bad))

    assert result.executed is False
    assert result.report.passed is False
    assert result.committed_solution is None
    assert np.allclose(before, gate.jog.committed_solution())


def test_joint_target_beyond_operational_does_not_execute(
    tight_operational_gate: NumericMoveTo,
) -> None:
    gate = tight_operational_gate
    # Home right joint4 is ~90°, outside this gate's [low, 45°] operational band.
    target = _home_right_joints(gate)
    before = gate.jog.committed_solution()

    result = gate.execute(JointMoveTo(side="right", joints_rad=target))

    assert result.executed is False
    assert np.allclose(before, gate.jog.committed_solution())


def test_unreachable_pose_does_not_execute(gate: NumericMoveTo) -> None:
    pose = gate.jog.current_pose("right", ReferenceFrame.WORLD, TcpSelection.FLANGE).copy()
    pose[0] += _UNREACHABLE_X_OFFSET_M
    before = gate.jog.committed_solution()

    result = gate.execute(PoseMoveTo(side="right", target_pose=tuple(pose.tolist())))

    assert result.executed is False
    assert result.report.ik_ok is False
    assert np.allclose(before, gate.jog.committed_solution())


def test_admissible_joint_target_executes(gate: NumericMoveTo) -> None:
    target = list(_home_right_joints(gate))
    target[1] += 0.05  # a small, in-limits nudge on joint2
    before = gate.jog.committed_solution()

    result = gate.execute(JointMoveTo(side="right", joints_rad=tuple(target)))

    assert result.executed is True
    assert result.report.passed is True
    assert result.committed_solution is not None
    assert not np.allclose(before, gate.jog.committed_solution())


def test_reachable_pose_executes(gate: NumericMoveTo) -> None:
    target = _reachable_pose(gate)

    result = gate.execute(PoseMoveTo(side="right", target_pose=target))

    assert result.executed is True
    achieved = gate.jog.current_pose("right", ReferenceFrame.WORLD, TcpSelection.FLANGE)
    assert float(np.linalg.norm(achieved[:3] - np.asarray(target[:3]))) < 3e-3
