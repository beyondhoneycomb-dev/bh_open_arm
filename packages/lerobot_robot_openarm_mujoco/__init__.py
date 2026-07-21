"""OpenArm MuJoCo backend -- a `lerobot_robot_*` third-party plugin (WP-0C-01).

`01` FR-SYS-014 extends LeRobot through plugins named `lerobot_robot_*`, never a
fork. This package is the MuJoCo backend (`09` FR-SIM-097, stage-1 canonical): the
`BiOpenArmMujoco` robot on the shared OpenArm Robot ABC, the `select_backend`
default-and-downgrade selector (`09` FR-SIM-102), and the SIM-mode CAN guard
(`09` FR-SIM-098).

The selector and CAN guard import no robot stack, so they stay usable in the light
lane. `BiOpenArmMujoco` and its config pull in LeRobot and `mujoco`, so they are
exposed lazily (PEP 562): importing this package costs nothing heavy until the
backend class is actually named.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from packages.lerobot_robot_openarm_mujoco.backend_selector import (
    Backend,
    BackendSelection,
    IsaacAvailability,
    isaac_version,
    mujoco_version,
    probe_isaac,
    select_backend,
)
from packages.lerobot_robot_openarm_mujoco.can_guard import (
    SimModeCanError,
    assert_no_can_open,
    open_can_in_sim,
)

if TYPE_CHECKING:
    from packages.lerobot_robot_openarm_mujoco.config_mujoco import BiOpenArmMujocoConfig
    from packages.lerobot_robot_openarm_mujoco.mujoco_backend import BiOpenArmMujoco

# The heavy (robot-stack) exports, resolved on first access so the light lane never
# imports LeRobot or mujoco just by importing this package.
_LAZY_EXPORTS = {
    "BiOpenArmMujoco": ("mujoco_backend", "BiOpenArmMujoco"),
    "BiOpenArmMujocoConfig": ("config_mujoco", "BiOpenArmMujocoConfig"),
}

__all__ = [
    "Backend",
    "BackendSelection",
    "BiOpenArmMujoco",
    "BiOpenArmMujocoConfig",
    "IsaacAvailability",
    "SimModeCanError",
    "assert_no_can_open",
    "isaac_version",
    "mujoco_version",
    "open_can_in_sim",
    "probe_isaac",
    "select_backend",
]


def __getattr__(name: str) -> Any:
    """Resolve the robot-stack exports lazily (PEP 562)."""
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = target
    from importlib import import_module

    module = import_module(f"{__name__}.{module_name}")
    return getattr(module, attribute)
