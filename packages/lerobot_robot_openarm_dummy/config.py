"""Plugin configs for the dummy follower and leader (FR-SYS-014, FR-SYS-003).

LeRobot is extended through its third-party plugin mechanism — a `lerobot_robot_*`
distribution that registers a `RobotConfig` choice — never by forking it. These two
configs register the `openarm_dummy` follower and its matching leader so the dummy
is selectable exactly the way a real backend is (`--robot.type=openarm_dummy`),
which is what makes the dummy↔real swap a config choice rather than a code edit.

The configs carry no fault-injection knobs on purpose: construction must be
identical in shape to a real follower/leader config, so a caller that builds one
can build the other with no changed line. Fault injection is a runtime affordance
set on the constructed object (`robot.fault`), not a declared config field.
"""

from __future__ import annotations

from dataclasses import dataclass

from lerobot.robots.config import RobotConfig
from lerobot.teleoperators.config import TeleoperatorConfig

# The LeRobot choice name this plugin registers under. It is the sole difference a
# caller states to pick the dummy over a real backend, and it is a CLI/config token,
# not a source line (acceptance ②).
DUMMY_ROBOT_TYPE = "openarm_dummy"
DUMMY_TELEOP_TYPE = "openarm_dummy_leader"


@RobotConfig.register_subclass(DUMMY_ROBOT_TYPE)
@dataclass
class DummyRobotConfig(RobotConfig):
    """Config for the dummy bimanual OpenArm follower.

    Shape-identical to a real follower config: only the base `id` and
    `calibration_dir` fields, plus the `use_velocity_and_torque` recording switch a
    real follower also carries (01 FR-SYS-012). No dummy-only field appears here.

    Attributes:
        use_velocity_and_torque: Whether velocity and torque channels are recorded.
            The observation schema is fixed at the full bimanual width regardless;
            this mirrors the real follower's switch so a paired leader can match it.
    """

    use_velocity_and_torque: bool = True


@TeleoperatorConfig.register_subclass(DUMMY_TELEOP_TYPE)
@dataclass
class DummyTeleoperatorConfig(TeleoperatorConfig):
    """Config for the dummy leader that drives the dummy follower.

    Attributes:
        use_velocity_and_torque: Must match the follower it is paired with
            (01 FR-SYS-012); a mismatch is a runtime KeyError in the record loop.
    """

    use_velocity_and_torque: bool = True
