"""The dummy OpenArm backend — a CAN-free drop-in for a real follower (WP-0C-05).

A dummy follower and leader that implement the real LeRobot ABCs and return the
frozen observation/action schema (WP-0A-02), so the whole teleop/record/inference
loop runs with no hardware and no CAN bus (FR-SIM-098). The dummy↔real swap is a
config choice, not a code edit (FR-SYS-003/002): the dummy opens no socket, spawns
no CLI, and imports no LeRobot in-tree loop.

Alongside the devices, a fault-injection scenario library drives six named failures
— obs-missing, packet-drop, stale-source, bus-off (simulated), partial-connect, and
response-lag — each through the real upstream that must react to it.
"""

from __future__ import annotations

from packages.lerobot_robot_openarm_dummy.canguard import (
    CanGuardReport,
    CanSocketOpenedError,
    forbid_can_sockets,
)
from packages.lerobot_robot_openarm_dummy.config import (
    DUMMY_ROBOT_TYPE,
    DUMMY_TELEOP_TYPE,
    DummyRobotConfig,
    DummyTeleoperatorConfig,
)
from packages.lerobot_robot_openarm_dummy.faults import (
    DropMonitor,
    FaultScenario,
    ObservationDeadlineMonitor,
    Reaction,
    scenario_library,
)
from packages.lerobot_robot_openarm_dummy.injection import (
    OBSERVATION_DEADLINE_SEC,
    FaultInjection,
    FaultKind,
)
from packages.lerobot_robot_openarm_dummy.robot import DummyOpenArmRobot, PartialConnectionError
from packages.lerobot_robot_openarm_dummy.schema import (
    REAL_OBSERVATION_FEATURES,
    frame_matches_schema,
    observation_field_diff,
)
from packages.lerobot_robot_openarm_dummy.staticcheck import (
    RULE_CAN_SYMBOL,
    RULE_CLI_SPAWN,
    RULE_INTREE_LOOP_IMPORT,
    Violation,
    check_package,
    check_source,
)
from packages.lerobot_robot_openarm_dummy.teleoperator import DummyOpenArmTeleoperator

__all__ = [
    "DUMMY_ROBOT_TYPE",
    "DUMMY_TELEOP_TYPE",
    "OBSERVATION_DEADLINE_SEC",
    "REAL_OBSERVATION_FEATURES",
    "RULE_CAN_SYMBOL",
    "RULE_CLI_SPAWN",
    "RULE_INTREE_LOOP_IMPORT",
    "CanGuardReport",
    "CanSocketOpenedError",
    "DropMonitor",
    "DummyOpenArmRobot",
    "DummyOpenArmTeleoperator",
    "DummyRobotConfig",
    "DummyTeleoperatorConfig",
    "FaultInjection",
    "FaultKind",
    "FaultScenario",
    "ObservationDeadlineMonitor",
    "PartialConnectionError",
    "Reaction",
    "Violation",
    "check_package",
    "check_source",
    "forbid_can_sockets",
    "frame_matches_schema",
    "observation_field_diff",
    "scenario_library",
]
