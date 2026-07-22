"""The jog API WP-2D-02 and WP-2D-09 consume, plus runtime IK-parameter exposure.

WP-2D-02 (singularity monitor + nullspace) reads the current arm joints, damps the jog
velocity, and installs a monitor that can hold the step. WP-2D-09 (numeric Move-to)
checks that an IK solution exists for an absolute pose before executing it, without
moving the arm during the check. The mink IK parameters are exposed at runtime through a
rebuild that keeps the committed pose and the fallback/residual settings.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from openarm_control.kinematics import IKParams

from backend.cartesian_jog import (
    JogAxis,
    JogCommand,
    JogKind,
    ReferenceFrame,
    TcpSelection,
    build_cartesian_jog,
)

_FAST = IKParams(max_iters=5, dt=0.1, damping=0.1, posture_cost=0.01, lm_damping=0.01)


def _z_jog() -> JogCommand:
    return JogCommand(side="right", kind=JogKind.TRANSLATION, axis=JogAxis.Z, sign=1)


# -- WP-2D-02 surface --------------------------------------------------------------


def test_arm_joints_expose_the_committed_seven_joint_state() -> None:
    jog = build_cartesian_jog(ik_params=_FAST)
    right = jog.arm_joints("right")
    assert right.shape == (7,)
    # Home has joint4 = pi/2; the rest zero.
    assert right[3] == pytest.approx(np.pi / 2, abs=1e-6)


def test_velocity_scale_damps_the_jog_increment() -> None:
    full = build_cartesian_jog(ik_params=_FAST)
    damped = build_cartesian_jog(ik_params=_FAST)
    start = full.current_pose("right", ReferenceFrame.WORLD, TcpSelection.FLANGE)[:3]

    damped.set_velocity_scale(0.1)
    full.step(_z_jog())
    damped.step(_z_jog())

    full_delta = np.linalg.norm(full.current_pose("right")[:3] - start)
    damped_delta = np.linalg.norm(damped.current_pose("right")[:3] - start)
    assert damped_delta < full_delta


def test_velocity_scale_rejects_out_of_range_values() -> None:
    jog = build_cartesian_jog(ik_params=_FAST)
    with pytest.raises(ValueError, match="velocity scale"):
        jog.set_velocity_scale(0.0)
    with pytest.raises(ValueError, match="velocity scale"):
        jog.set_velocity_scale(1.5)


def test_singularity_monitor_can_hold_or_pass_a_step() -> None:
    jog = build_cartesian_jog(ik_params=_FAST)

    holds: list[bool] = [False]

    def monitor(side: str, joints: np.ndarray) -> str | None:
        return "held" if holds[0] else None

    jog.set_singularity_monitor(monitor)
    assert jog.step(_z_jog()).committed is True
    holds[0] = True
    assert jog.step(_z_jog()).stopped is True


# -- WP-2D-09 surface --------------------------------------------------------------


def test_ik_existence_check_does_not_move_the_arm() -> None:
    jog = build_cartesian_jog(ik_params=_FAST)
    reachable = jog.current_pose("right", ReferenceFrame.WORLD, TcpSelection.FLANGE).copy()
    reachable[2] += 0.03
    before = jog.committed_solution()

    exists = jog.ik_solution_exists("right", reachable)

    assert exists is True
    assert np.allclose(before, jog.committed_solution())


def test_ik_existence_check_rejects_an_unreachable_pose() -> None:
    jog = build_cartesian_jog(ik_params=_FAST)
    unreachable = jog.current_pose("right", ReferenceFrame.WORLD, TcpSelection.FLANGE).copy()
    unreachable[0] += 3.0
    assert jog.ik_solution_exists("right", unreachable) is False


def test_move_to_commits_only_when_the_target_is_reached() -> None:
    jog = build_cartesian_jog(ik_params=_FAST)
    target = jog.current_pose("right", ReferenceFrame.WORLD, TcpSelection.FLANGE).copy()
    target[2] += 0.03

    result = jog.plan_pose("right", target, commit=True)

    assert result.committed is True
    achieved = jog.current_pose("right", ReferenceFrame.WORLD, TcpSelection.FLANGE)
    assert float(np.linalg.norm(achieved[:3] - target[:3])) < 3e-3


# -- runtime IK-parameter exposure -------------------------------------------------


def test_ik_params_rebuild_preserves_state_and_settings() -> None:
    jog = build_cartesian_jog(
        ik_params=_FAST, allow_unconstrained_fallback=False, residual_max_m=0.02
    )
    jog.step(_z_jog())
    committed = jog.committed_solution()

    jog.set_ik_params(IKParams(max_iters=2, dt=0.05, damping=0.2))

    assert jog.ik_params.max_iters == 2
    assert jog.ik_params.dt == pytest.approx(0.05)
    assert jog.allow_unconstrained_fallback is False
    assert np.allclose(committed, jog.committed_solution())
    # The jog still runs after the rebuild.
    assert jog.step(_z_jog()).committed is True
