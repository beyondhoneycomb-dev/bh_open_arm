"""Acceptance ① -- the Robot ABC is fully implemented, zero unimplemented signatures.

The backend must resolve every abstract method LeRobot's `Robot` declares, be a
concrete (instantiable) class, and run each method without a `NotImplementedError`.
These go through the real LeRobot ABC and the real MJCF, so the module skips where
the robot stack or MuJoCo is absent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("mujoco")
pytest.importorskip("lerobot")

from lerobot.robots.robot import Robot  # noqa: E402
from lerobot.utils.errors import (  # noqa: E402
    DeviceAlreadyConnectedError,
    DeviceNotConnectedError,
)

from packages.lerobot_robot_openarm_mujoco import (  # noqa: E402
    BiOpenArmMujoco,
    BiOpenArmMujocoConfig,
)
from sim.mujoco.sim_sync import action_channel_order  # noqa: E402


def _backend(calibration_dir: Path) -> BiOpenArmMujoco:
    return BiOpenArmMujoco(BiOpenArmMujocoConfig(id="wp0c01", calibration_dir=calibration_dir))


def test_backend_is_concrete_not_abstract() -> None:
    assert BiOpenArmMujoco.__abstractmethods__ == frozenset()
    assert issubclass(BiOpenArmMujoco, Robot)


def test_every_robot_abstract_method_is_overridden() -> None:
    # Each Robot abstract member must resolve, through the MRO, to something other
    # than Robot's abstract stub. The frozen feature properties come from the shared
    # OpenArmRobot base by design; the rest come from BiOpenArmMujoco itself.
    for name in Robot.__abstractmethods__:
        assert getattr(BiOpenArmMujoco, name) is not getattr(Robot, name), (
            f"{name} still resolves to Robot's abstract stub"
        )


def test_config_class_and_name_are_declared() -> None:
    assert BiOpenArmMujoco.config_class is BiOpenArmMujocoConfig
    assert BiOpenArmMujoco.name == "bi_openarm_mujoco"


def test_lifecycle_methods_run_without_notimplemented(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    assert backend.is_connected is False
    assert backend.is_calibrated is True

    backend.calibrate()  # no-op, must not raise
    backend.connect()
    assert backend.is_connected is True

    backend.configure()  # reset, must not raise
    observation = backend.get_observation()
    assert observation  # non-empty

    action = dict.fromkeys(action_channel_order(), 0.0)
    sent = backend.send_action(action)
    assert set(sent) == set(action)

    backend.disconnect()
    assert backend.is_connected is False


def test_observation_and_action_before_connect_raise(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    with pytest.raises(DeviceNotConnectedError):
        backend.get_observation()
    with pytest.raises(DeviceNotConnectedError):
        backend.send_action(dict.fromkeys(action_channel_order(), 0.0))


def test_double_connect_and_orphan_disconnect_raise(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    backend.connect()
    with pytest.raises(DeviceAlreadyConnectedError):
        backend.connect()
    backend.disconnect()
    with pytest.raises(DeviceNotConnectedError):
        backend.disconnect()


def test_feature_dicts_are_the_frozen_contract(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    # 16 position-only action channels; 48 observation channels + drop-counter meta.
    assert len(backend.action_features) == 16
    assert len(backend.observation_features) == 49
