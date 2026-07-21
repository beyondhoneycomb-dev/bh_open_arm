"""Acceptance ⑨/⑩ — the twin is read-only, stiff-gated, and uvt-gated."""

from __future__ import annotations

from pathlib import Path

import pytest

import sim.dryrun.twin as twin_module
from packages.lerobot_robot_openarm_dummy import DummyOpenArmRobot
from packages.lerobot_robot_openarm_dummy.config import DummyRobotConfig
from sim.dryrun.staticcheck import check_twin_no_send_action
from sim.dryrun.twin import (
    STIFF_KP,
    DigitalTwin,
    GainParityError,
    VelocityTorqueDisabledError,
    verify_stiff_gain_parity,
)
from sim.mujoco.scene import MujocoScene

# A compliant (70-series) profile — the v1/v2 common default, not the v2 stiff canon.
_COMPLIANT_KP = (70.0, 70.0, 70.0, 70.0, 70.0, 70.0, 70.0, 10.0)


def _named_left_j1_source() -> dict[str, float]:
    """A canned observation putting left_joint_1 at 30 degrees, the rest at zero."""
    observation = {f"{side}_joint_{n}.pos": 0.0 for side in ("left", "right") for n in range(1, 8)}
    observation.update({f"{side}_gripper.pos": 0.0 for side in ("left", "right")})
    observation["left_joint_1.pos"] = 30.0
    return observation


def test_verify_stiff_gain_parity_accepts_the_canon() -> None:
    """⑩ The stiff (230-series) profile passes the parity check."""
    verify_stiff_gain_parity(STIFF_KP)


def test_twin_refuses_compliant_gains() -> None:
    """⑩ A compliant (70-series) arm poisons the residual → twin refuses."""
    with pytest.raises(GainParityError):
        verify_stiff_gain_parity(_COMPLIANT_KP)
    scene = MujocoScene.load()
    with pytest.raises(GainParityError):
        DigitalTwin(scene, dict, use_velocity_and_torque=True, real_arm_kp=_COMPLIANT_KP)


def test_twin_refuses_without_velocity_and_torque() -> None:
    """⑩ use_velocity_and_torque=false → twin refuses to start (FR-SIM-025b)."""
    scene = MujocoScene.load()
    with pytest.raises(VelocityTorqueDisabledError):
        DigitalTwin(scene, dict, use_velocity_and_torque=False, real_arm_kp=STIFF_KP)


def test_twin_mirrors_dummy_observation_read_only() -> None:
    """⑨ The twin mirrors WP-0C-05 dummy observations without commanding anything."""
    robot = DummyOpenArmRobot(DummyRobotConfig())
    robot.connect()
    scene = MujocoScene.load()
    twin = DigitalTwin(
        scene, robot.get_observation, use_velocity_and_torque=True, real_arm_kp=STIFF_KP
    )
    mirrored = twin.mirror()
    assert len(mirrored) == 16
    assert all(isinstance(value, float) for value in mirrored.values())


def test_twin_mirror_writes_the_mirrored_position() -> None:
    """⑨ A 30-degree source position lands as ~0.5236 rad in the scene state."""
    scene = MujocoScene.load()
    twin = DigitalTwin(
        scene, _named_left_j1_source, use_velocity_and_torque=True, real_arm_kp=STIFF_KP
    )
    twin.mirror()
    position_rad, _, _ = scene.read_joint_state()["left_joint_1"]
    assert position_rad == pytest.approx(0.5235987, abs=1e-5)


def test_twin_source_has_no_send_action_symbol() -> None:
    """⑨ Static: the twin path references no send_action."""
    source = Path(twin_module.__file__).read_text(encoding="utf-8")
    assert check_twin_no_send_action(source, twin_module.__file__) == []
