"""The numeric inputs reject a malformed request at construction.

A wrong-width joint vector or pose, or an unknown side, is refused when the request is
built — before any check runs — so the gate never has to reason about a shape it cannot
map onto the arm. The gate also refuses a clamp envelope that is not the bimanual width
the committed solution uses.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("openarm_control")
pytest.importorskip("lerobot")

from backend.actuation.safety import SafetyLimits
from backend.cartesian_jog import build_cartesian_jog
from backend.jogclamp import JogClampPath
from backend.moveto import JointMoveTo, NumericMoveTo, PoseMoveTo
from contracts.units import Deg, Nm


def test_joint_request_rejects_wrong_width() -> None:
    with pytest.raises(ValueError, match="7-wide"):
        JointMoveTo(side="right", joints_rad=(0.0, 0.0, 0.0))


def test_joint_request_rejects_unknown_side() -> None:
    with pytest.raises(ValueError, match="side must be"):
        JointMoveTo(side="middle", joints_rad=(0.0,) * 7)


def test_pose_request_rejects_wrong_width() -> None:
    with pytest.raises(ValueError, match="7-vector"):
        PoseMoveTo(side="right", target_pose=(0.0, 0.0, 0.0))


def test_gate_rejects_non_bimanual_envelope() -> None:
    three_joint = SafetyLimits(
        mechanical_deg=((Deg(-180.0), Deg(180.0)),) * 3,
        operational_deg=((Deg(-90.0), Deg(90.0)),) * 3,
        velocity_limit_rad_s=(1.0, 1.0, 1.0),
        accel_limit_rad_s2=(5.0, 5.0, 5.0),
        jerk_limit_rad_s3=(50.0, 50.0, 50.0),
        step_delta_limit_rad=(0.1, 0.1, 0.1),
        peak_torque_nm=(Nm(10.0), Nm(10.0), Nm(10.0)),
        operational_torque_nm=(Nm(10.0), Nm(10.0), Nm(10.0)),
    )
    jog = build_cartesian_jog()
    with pytest.raises(ValueError, match="bimanual"):
        NumericMoveTo(jog=jog, clamp=JogClampPath(three_joint))
