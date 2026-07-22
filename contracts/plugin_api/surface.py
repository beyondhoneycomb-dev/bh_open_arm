"""The frozen CTR-PLUG@v1 API surface, derived from the shared Robot ABC (09 FR-SIM-097).

CTR-PLUG@v1 promises that every backend — hardware follower, MuJoCo, Isaac, dummy —
implements ONE Robot ABC surface: LeRobot's abstract method set, with the
observation/action feature contract fixed at the frozen 48/16 channel widths. This
module derives that surface from `contracts.plugin.robot_abc.OpenArmRobot` rather
than restating it, so the freeze re-confirmation (and any future change detection)
reads one definition of what the plugin API is.

Importing this module imports the robot stack (LeRobot, via `robot_abc`); it is the
hardware-axis re-confirmation surface WP-1-01 owns, and runs in the robot lane.
"""

from __future__ import annotations

from lerobot.robots.robot import Robot

from contracts.plugin.robot_abc import (
    OpenArmRobot,
    openarm_action_features,
    openarm_observation_features,
)

# The frozen bimanual channel widths CTR-PLUG@v1 fixes: 48 observation.state
# channels plus the CAN drop-counter meta, and the 16 position-only action channels
# (10 FR-TRN-066). A backend that reports a different width has broken the contract.
FROZEN_OBSERVATION_WIDTH = 49
FROZEN_ACTION_WIDTH = 16


def frozen_abc_methods() -> frozenset[str]:
    """Return the full LeRobot Robot ABC method/property surface.

    Returns:
        (frozenset[str]) Every abstract member a Robot must supply.
    """
    return frozenset(Robot.__abstractmethods__)


def features_fixed_by_openarm() -> frozenset[str]:
    """Return the surface members OpenArmRobot freezes for every backend.

    These are the members `OpenArmRobot` implements so subclasses cannot redeclare
    them — the observation/action feature contract that keeps every backend on one
    schema (09 FR-SIM-097).

    Returns:
        (frozenset[str]) Members frozen at the ABC, absent from a subclass's
            remaining abstract set.
    """
    return frozenset(Robot.__abstractmethods__) - frozenset(OpenArmRobot.__abstractmethods__)


def backend_must_implement() -> frozenset[str]:
    """Return the members a concrete backend still has to implement itself.

    Returns:
        (frozenset[str]) Abstract members left open by `OpenArmRobot` (connect,
            disconnect, calibrate, configure, get_observation, send_action, and the
            two connection/calibration flags).
    """
    return frozenset(OpenArmRobot.__abstractmethods__)


def observation_width(bimanual: bool = True) -> int:
    """Return the observation feature count the frozen schema produces.

    Args:
        bimanual: Whether to measure the bimanual (48+1) or single-arm surface.

    Returns:
        (int) Number of observation feature channels including the drop counter.
    """
    return len(openarm_observation_features(bimanual=bimanual))


def action_width(bimanual: bool = True) -> int:
    """Return the action feature count the frozen schema produces.

    Args:
        bimanual: Whether to measure the bimanual (16) or single-arm (8) surface.

    Returns:
        (int) Number of position-only action feature channels.
    """
    return len(openarm_action_features(bimanual=bimanual))
