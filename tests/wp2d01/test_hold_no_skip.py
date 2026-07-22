"""Acceptance ④ — an IK failure holds immediately with a reason; zero steps are skipped.

The upstream ``_IKSolver.solve`` prints "Skipping step" and returns None, so a naive
jog loop would drop the failed step and roll on. This jog does the opposite: a failed
step never advances the committed pose, latches the jog stopped, and reports a
categorized reason (``NoSolutionFound`` / limit / singularity). A subsequent command
while latched does not move the arm — the failure is a hold, not a skip.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from openarm_control.kinematics import IKParams

from backend.cartesian_jog import JogAxis, JogCommand, JogKind, build_cartesian_jog
from backend.cartesian_jog.jog import JogStopReason
from sim.ik.limits import all_soft_limits

_FAST = {"dt": 0.1, "damping": 0.1, "posture_cost": 0.01, "lm_damping": 0.01}


def _out_of_limit_config() -> np.ndarray:
    upper = np.array([limit.upper_rad.value for limit in all_soft_limits()], dtype=float)
    return upper + 1.0


def _z_jog() -> JogCommand:
    return JogCommand(side="right", kind=JogKind.TRANSLATION, axis=JogAxis.Z, sign=1)


def test_failure_holds_immediately_with_a_categorized_reason() -> None:
    jog = build_cartesian_jog(ik_params=IKParams(max_iters=3, **_FAST))
    jog.seed(_out_of_limit_config())

    result = jog.step(_z_jog())

    assert result.stopped is True
    assert result.committed is False
    assert result.reason is JogStopReason.NO_SOLUTION
    assert jog.stopped is True
    assert jog.stop_reason is JogStopReason.NO_SOLUTION


def test_zero_steps_skipped_on_failure() -> None:
    jog = build_cartesian_jog(ik_params=IKParams(max_iters=3, **_FAST))
    jog.seed(_out_of_limit_config())
    before = jog.committed_solution()

    first = jog.step(_z_jog())
    # A held step advances nothing and is counted as held, never silently skipped.
    assert first.committed is False
    assert jog.steps_committed == 0
    assert jog.steps_held == 1
    assert np.allclose(before, jog.committed_solution())

    # A second command while latched still does not move the arm.
    second = jog.step(_z_jog())
    assert second.stopped is True
    assert second.committed is False
    assert np.allclose(before, jog.committed_solution())


def test_resume_clears_the_latch_and_lets_a_valid_step_through() -> None:
    jog = build_cartesian_jog(ik_params=IKParams(max_iters=5, **_FAST))
    jog.seed(_out_of_limit_config())
    assert jog.step(_z_jog()).stopped is True

    # Re-seed to a valid pose and resume: the jog runs again with no residue.
    from backend.cartesian_jog.frames import KinematicFrames

    jog.seed(KinematicFrames().home_solution())
    assert jog.stopped is False
    result = jog.step(_z_jog())
    assert result.committed is True
    assert result.reason is None


def test_singularity_reason_is_available_for_the_wp2d02_monitor() -> None:
    jog = build_cartesian_jog(ik_params=IKParams(max_iters=5, **_FAST))

    def monitor(side: str, joints: np.ndarray) -> str | None:
        return "min singular value below threshold"

    jog.set_singularity_monitor(monitor)
    result = jog.step(_z_jog())

    assert result.stopped is True
    assert result.reason is JogStopReason.SINGULARITY
    assert "singular" in result.detail
    # The five reason categories are distinct, so a monitor's stop is never confused
    # with an IK-fault stop.
    assert len({reason.value for reason in JogStopReason}) == len(JogStopReason)
