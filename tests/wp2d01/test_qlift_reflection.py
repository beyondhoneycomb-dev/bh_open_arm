"""Acceptance ⑤ — the q_lift reflection removes a systematic error up to the lifter travel.

``sim.ik`` freezes the lifter and solves with the base at the home height, so a
physical-world target the operator commands must be reflected onto that IK world by the
lifter displacement. Skipping the reflection leaves a systematic error equal to the
lifter position — up to its full 0.3 m travel — and the reflection drives it to zero.
Measured against the model's own forward kinematics, not an assumed number.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from backend.cartesian_jog import build_cartesian_jog
from backend.cartesian_jog.frames import KinematicFrames

_SIDE = "right"


def _errors_at(q_lift: float) -> tuple[float, float, float]:
    """Return (unreflected error, reflected error, lifter displacement) at a lift."""
    jog = build_cartesian_jog()
    frames = jog._frames
    home = jog.committed_solution()

    # Physical-world TCP at this lift vs the IK world (base at lift zero).
    physical = frames.control_point_pose(_SIDE, home, q_lift)
    ik_world = frames.control_point_pose(_SIDE, home, 0.0)

    jog.set_q_lift(q_lift)
    reflected = jog.reflect_world_to_ik(_SIDE, physical)

    unreflected_error = float(np.linalg.norm(physical[:3] - ik_world[:3]))
    reflected_error = float(np.linalg.norm(reflected[:3] - ik_world[:3]))
    displacement = float(np.linalg.norm(frames.lift_offset_world(_SIDE, q_lift)))
    return unreflected_error, reflected_error, displacement


# The cell FK poses are float32 (openarm_control.read_ee_pose), so a "vanished" error
# is float32 zero — a few 1e-8, not machine double zero. The reflection removes ~0.3 m
# and leaves this residue; the tolerance is the sensor of that, not slack.
_FLOAT32_POSE_TOL_M = 1e-5


def test_unreflected_error_reproduces_the_full_lifter_travel() -> None:
    _, high = KinematicFrames().lifter_range
    assert high == pytest.approx(0.3)

    unreflected, reflected, displacement = _errors_at(high)

    # The error the reflection removes equals the lifter displacement, up to 0.3 m.
    assert unreflected == pytest.approx(displacement, abs=_FLOAT32_POSE_TOL_M)
    assert unreflected == pytest.approx(0.3, abs=1e-4)
    assert reflected < _FLOAT32_POSE_TOL_M


def test_error_is_systematic_and_scales_with_lift() -> None:
    for q_lift in (0.05, 0.15, 0.3):
        unreflected, reflected, _ = _errors_at(q_lift)
        assert unreflected == pytest.approx(q_lift, abs=1e-4)
        assert reflected < _FLOAT32_POSE_TOL_M


def test_reflection_at_zero_lift_is_identity() -> None:
    unreflected, reflected, displacement = _errors_at(0.0)
    assert displacement == pytest.approx(0.0, abs=_FLOAT32_POSE_TOL_M)
    assert unreflected < _FLOAT32_POSE_TOL_M
    assert reflected < _FLOAT32_POSE_TOL_M
