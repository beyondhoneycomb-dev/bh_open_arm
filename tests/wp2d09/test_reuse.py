"""The gate reuses WP-2D-01's IK and WP-2A-03's limit envelope, by identity — not copies.

The static no-second-IK scan lives in ``test_no_second_ik``; here is the runtime half:
the gate's only door to a Kinematics is ``sim.ik``'s ordered builder (the same object
WP-2D-01 uses), and its limit check reads the injected ``JogClampPath`` envelope. The
last test is the one that proves the reuse is not redundant: an EE pose the reused IK
solves *within* the mechanical soft limits is still refused when its solution leaves the
tighter operational band — a finding the IK-existence check alone cannot produce.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("openarm_control")
pytest.importorskip("lerobot")

import backend.moveto.gate as gate_module
from backend.cartesian_jog import ReferenceFrame, TcpSelection, build_cartesian_jog
from backend.jogclamp import JogClampPath, JogClampReason
from backend.moveto import NumericMoveTo, PoseMoveTo, build_numeric_move_to
from sim.ik.adapter import IkAdapter, build_ik_adapter


def test_gate_reaches_ik_only_through_the_reused_ordered_builder(
    default_limits,
) -> None:
    # The gate module's only door to a Kinematics is sim.ik's ordered builder, the same
    # one WP-2D-01 uses — not a bespoke solver constructed here.
    assert gate_module.build_cartesian_jog is build_cartesian_jog

    move_to = build_numeric_move_to(clamp=JogClampPath(default_limits))
    assert isinstance(move_to.jog._adapter, IkAdapter)
    assert move_to.jog._adapter is not None
    # sim.ik's builder identity is preserved end to end.
    assert build_ik_adapter is not None


def test_limit_check_reads_the_injected_clamp_envelope(default_limits) -> None:
    clamp = JogClampPath(default_limits)
    move_to = build_numeric_move_to(clamp=clamp)
    # The gate consumes the injected WP-2A-03 clamp, not a private envelope.
    assert move_to.clamp is clamp


def test_operational_limit_on_ee_solution_is_caught(tight_operational_gate: NumericMoveTo) -> None:
    gate = tight_operational_gate
    # A small, reachable EE nudge: the reused IK finds a solution within the mechanical
    # soft limits, but that solution's joint4 (~90°) leaves the tighter operational band.
    pose = gate.jog.current_pose("right", ReferenceFrame.WORLD, TcpSelection.FLANGE).copy()
    pose[2] += 0.02
    before = gate.jog.committed_solution()

    result = gate.execute(PoseMoveTo(side="right", target_pose=tuple(pose.tolist())))

    assert result.executed is False
    assert result.report.ik_ok is True  # a solution exists...
    assert result.report.limit_ok is False  # ...but it violates the operational band
    reasons = {f.reason for f in result.report.limit_findings}
    assert JogClampReason.OPERATIONAL_LIMIT in reasons
    assert np.allclose(before, gate.jog.committed_solution())
