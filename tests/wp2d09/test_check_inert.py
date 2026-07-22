"""``check`` is inert — running the checks never moves the committed arm state.

The gate can only guarantee "execute only on pass" if the check itself has no side
effect; otherwise a probe would be a hidden move. Every check path — a passing and a
failing joint target, a reachable and an unreachable pose — must leave the committed
solution byte-for-byte unchanged, including the EE probe that drives the solver and then
restores it.
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


def test_passing_joint_check_moves_nothing(gate: NumericMoveTo) -> None:
    before = gate.jog.committed_solution()
    gate.check(JointMoveTo(side="right", joints_rad=_home_right_joints(gate)))
    assert np.allclose(before, gate.jog.committed_solution())


def test_failing_joint_check_moves_nothing(gate: NumericMoveTo) -> None:
    bad = (_MECHANICAL_OVERSHOOT_RAD,) + _home_right_joints(gate)[1:]
    before = gate.jog.committed_solution()
    gate.check(JointMoveTo(side="right", joints_rad=bad))
    assert np.allclose(before, gate.jog.committed_solution())


def test_reachable_pose_check_moves_nothing(gate: NumericMoveTo) -> None:
    pose = gate.jog.current_pose("right", ReferenceFrame.WORLD, TcpSelection.FLANGE).copy()
    pose[2] += _REACHABLE_Z_OFFSET_M
    before = gate.jog.committed_solution()
    report = gate.check(PoseMoveTo(side="right", target_pose=tuple(pose.tolist())))
    assert report.passed is True
    assert np.allclose(before, gate.jog.committed_solution())


def test_unreachable_pose_check_moves_nothing(gate: NumericMoveTo) -> None:
    pose = gate.jog.current_pose("right", ReferenceFrame.WORLD, TcpSelection.FLANGE).copy()
    pose[0] += _UNREACHABLE_X_OFFSET_M
    before = gate.jog.committed_solution()
    gate.check(PoseMoveTo(side="right", target_pose=tuple(pose.tolist())))
    assert np.allclose(before, gate.jog.committed_solution())
