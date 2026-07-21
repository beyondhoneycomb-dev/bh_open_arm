"""The shared Robot ABC binds the frozen schema, no adapter layer (WP-0A-02).

FR-SIM-097 / FR-SYS-014: MuJoCo, Isaac, and the hardware follower share the SAME
LeRobot `Robot` ABC — a backend implementing it is a drop-in, with no separate
adapter layer, and LeRobot is extended by plugin, not by forking. This asserts the
shared base subclasses LeRobot's `Robot`, stays abstract (it is a contract, not a
runnable robot), and reports the frozen feature contract: 48 observation channels
plus the drop-counter meta, and 16 position-only action channels.

This module imports LeRobot; it is skipped when the robot stack is not installed,
so the light lane stays green.
"""

from __future__ import annotations

import pytest

pytest.importorskip("lerobot", reason="CTR-PLUG Robot ABC needs the LeRobot stack")

from lerobot.robots.robot import Robot  # noqa: E402

from contracts.action import BIMANUAL_ACTION_DIM, DROP_COUNTER_META  # noqa: E402
from contracts.action.observation import BIMANUAL_OBSERVATION_DIM  # noqa: E402
from contracts.plugin.robot_abc import (  # noqa: E402
    OpenArmRobot,
    openarm_action_features,
    openarm_observation_features,
)


def test_shared_base_is_a_lerobot_robot() -> None:
    """The OpenArm base subclasses LeRobot's Robot ABC (no separate adapter)."""
    assert issubclass(OpenArmRobot, Robot)


def test_shared_base_stays_abstract() -> None:
    """The base cannot be instantiated — it freezes a contract, not a robot."""
    assert OpenArmRobot.__abstractmethods__
    with pytest.raises(TypeError):
        OpenArmRobot(None)  # type: ignore[abstract, arg-type]


def test_observation_features_preserve_48_plus_drop_meta() -> None:
    """Observation features are the 48 preserved channels plus the drop counter."""
    features = openarm_observation_features(bimanual=True)
    assert len(features) == BIMANUAL_OBSERVATION_DIM + 1
    assert DROP_COUNTER_META in features


def test_action_features_are_16_position_only() -> None:
    """Action features are the 16 position channels — velocity and torque excluded."""
    features = openarm_action_features(bimanual=True)
    assert len(features) == BIMANUAL_ACTION_DIM
    assert all(name.endswith(".pos") for name in features)
