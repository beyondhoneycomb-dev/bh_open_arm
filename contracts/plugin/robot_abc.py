"""The shared OpenArm Robot ABC (CTR-PLUG@v1, FR-SIM-097 / FR-SYS-014).

MuJoCo and Isaac backends, and the hardware follower, all implement the SAME
LeRobot `Robot` ABC (09 FR-SIM-097): there is no separate adapter layer — a
backend that implements this interface is a drop-in. LeRobot itself is extended
through its third-party plugin mechanism (`lerobot_robot_*`, 01 FR-SYS-014), not
by forking it, so this base subclasses LeRobot's `Robot` directly rather than
wrapping it.

This module binds the frozen action/observation schema (CTR-ACT@v1) to the LeRobot
feature dictionaries: `observation_features` is the 48 preserved channels plus the
CAN drop-counter meta, and `action_features` is the 16 position-only channels —
the training target. Deriving both from the frozen schema is what keeps every
backend reporting the same joint, camera, and unit contract (FR-SIM-097).

Importing this module imports the robot stack (LeRobot); it is product code, not
plan-machine code, so that is allowed. The pure config validation that the
acceptance fixtures exercise lives in `contracts.plugin.config`, which imports no
robot stack.
"""

from __future__ import annotations

from lerobot.robots.robot import Robot

from contracts.action.observation import DROP_COUNTER_META, raw_observation_channels

# LeRobot feature dicts map a channel name to the Python type of a scalar sample;
# every proprioceptive channel is a float, and the drop counter is an int count.
_SCALAR_FEATURE_TYPE = float
_COUNTER_FEATURE_TYPE = int

# The observation suffix that is the position action target (position-only action).
_POSITION_SUFFIX = "pos"


def openarm_observation_features(bimanual: bool = True) -> dict[str, type]:
    """Return the LeRobot observation feature dict for the OpenArm follower.

    Every one of the 48 (bimanual) observation.state channels is preserved and
    named, plus the CAN packet drop counter as observation meta (01 FR-SYS-018).

    Args:
        bimanual: Whether to build the 48-channel bimanual features or 24 single arm.

    Returns:
        (dict[str, type]) Channel name to scalar feature type.
    """
    features: dict[str, type] = {
        channel.name: _SCALAR_FEATURE_TYPE
        for channel in raw_observation_channels(bimanual=bimanual)
    }
    features[DROP_COUNTER_META] = _COUNTER_FEATURE_TYPE
    return features


def openarm_action_features(bimanual: bool = True) -> dict[str, type]:
    """Return the LeRobot action feature dict — position-only (10 FR-TRN-066).

    The action is the 16 (bimanual) position channels: exactly the `.pos` channels
    of the observation vector, so action index and observation position index name
    the same joint. Velocity and torque are never action features.

    Args:
        bimanual: Whether to build the 16-channel bimanual action or 8 single arm.

    Returns:
        (dict[str, type]) Position channel name to scalar feature type.
    """
    return {
        channel.name: _SCALAR_FEATURE_TYPE
        for channel in raw_observation_channels(bimanual=bimanual)
        if channel.suffix == _POSITION_SUFFIX
    }


class OpenArmRobot(Robot):
    """The frozen OpenArm Robot ABC shared by every backend (FR-SIM-097).

    Concrete backends — `BiOpenArmMujoco` (1단계 정본), `BiOpenArmIsaac` (2단계
    선택), and the hardware follower — subclass this and implement the remaining
    LeRobot abstract methods (`connect`, `disconnect`, `calibrate`, `configure`,
    `get_observation`, `send_action`, `is_connected`, `is_calibrated`). They must
    not redeclare the feature contract: it is frozen here so all backends share one
    joint and unit contract. This class stays abstract; it is a contract, not a
    runnable robot.
    """

    @property
    def observation_features(self) -> dict[str, type]:
        """The frozen 48-channel observation features plus drop-counter meta."""
        return openarm_observation_features(bimanual=True)

    @property
    def action_features(self) -> dict[str, type]:
        """The frozen 16-channel position-only action features (training target)."""
        return openarm_action_features(bimanual=True)
