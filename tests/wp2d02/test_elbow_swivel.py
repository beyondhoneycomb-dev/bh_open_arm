"""Acceptance ① — the elbow swivel moves the arm while the EE pose stays fixed (by FK).

The swivel walks the arm along the Jacobian nullspace and re-fixes the EE through the
reused jog IK. So two things must both hold: the arm genuinely moves (a nullspace that
did nothing would be a broken slider) and the EE does not (a nullspace that moved the EE
is the RETRY_WITH_VARIANT failure). EE drift is read back from the jog's own forward
kinematics against the pose captured before the swivel. A swivel the IK cannot satisfy
restores the arm exactly, returning the EE to where it began.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from backend.cartesian_jog import (
    JogAxis,
    JogCommand,
    JogKind,
    ReferenceFrame,
    TcpSelection,
    build_cartesian_jog,
)
from backend.cartesian_jog.frames import pose_position, pose_quat, quat_geodesic_angle
from backend.singularity import build_elbow_swivel
from backend.singularity.constants import EE_FIXED_TOLERANCE_M, EE_FIXED_TOLERANCE_RAD


def _jogged_off_home(side: str = "right", steps: int = 6):
    """Build a jog moved off the home pose so the arm has swivel room."""
    jog = build_cartesian_jog()
    command = JogCommand(side=side, kind=JogKind.TRANSLATION, axis=JogAxis.Y, sign=-1)
    for _ in range(steps):
        jog.step(command)
    return jog


def _ee_drift(jog, side, frozen):
    """Return (translation_m, rotation_rad) of the current TCP pose from ``frozen``, by FK."""
    now = jog.current_pose(side, ReferenceFrame.WORLD, TcpSelection.FLANGE)
    return (
        float(np.linalg.norm(pose_position(now) - pose_position(frozen))),
        quat_geodesic_angle(pose_quat(now), pose_quat(frozen)),
    )


@pytest.mark.parametrize("side", ["right", "left"])
@pytest.mark.parametrize("delta", [0.1, 0.3, -0.2])
def test_swivel_moves_the_arm_but_holds_the_ee_fixed(side: str, delta: float) -> None:
    jog = _jogged_off_home(side)
    frozen = jog.current_pose(side, ReferenceFrame.WORLD, TcpSelection.FLANGE)
    swivel = build_elbow_swivel(jog)

    result = swivel.swivel(side, delta)

    assert result.applied
    # The arm moved (real elbow self-motion, not a no-op).
    assert result.arm_delta_rad > 0.5 * abs(delta)
    # The EE did not (acceptance ①), by the result and by an independent FK read.
    assert result.ee_translation_drift_m < EE_FIXED_TOLERANCE_M
    assert result.ee_rotation_drift_rad < EE_FIXED_TOLERANCE_RAD
    drift_m, drift_rad = _ee_drift(jog, side, frozen)
    assert drift_m < EE_FIXED_TOLERANCE_M
    assert drift_rad < EE_FIXED_TOLERANCE_RAD


def test_swivel_is_directional() -> None:
    # Opposite signs push the elbow opposite ways through the nullspace.
    positive = _jogged_off_home()
    start = positive.committed_solution()[0:7].copy()
    build_elbow_swivel(positive).swivel("right", 0.3)
    move_plus = positive.committed_solution()[0:7] - start

    negative = _jogged_off_home()
    build_elbow_swivel(negative).swivel("right", -0.3)
    move_minus = negative.committed_solution()[0:7] - start

    assert float(np.dot(move_plus, move_minus)) < 0.0


def test_zero_swivel_is_a_noop() -> None:
    jog = _jogged_off_home()
    before = jog.committed_solution()
    result = build_elbow_swivel(jog).swivel("right", 0.0)
    assert result.applied and result.substeps == 0 and result.arm_delta_rad == 0.0
    assert np.array_equal(jog.committed_solution(), before)


def test_rejected_swivel_restores_the_configuration_and_the_ee() -> None:
    # A swivel too large to satisfy holds and restores the pre-swivel arm exactly, so the
    # EE returns to where it started rather than staying at the drifted seed.
    jog = _jogged_off_home()
    before = jog.committed_solution()
    frozen = jog.current_pose("right", ReferenceFrame.WORLD, TcpSelection.FLANGE)

    result = build_elbow_swivel(jog).swivel("right", 5.0)

    assert not result.applied and result.reason is not None
    assert np.array_equal(jog.committed_solution(), before)
    drift_m, drift_rad = _ee_drift(jog, "right", frozen)
    assert drift_m < 1e-9 and drift_rad < 1e-9
