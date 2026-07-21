"""Config for the MuJoCo bimanual backend (CTR-PLUG@v1 / `09` FR-SIM-097).

A LeRobot `RobotConfig` subclass registered as `bi_openarm_mujoco`, so the backend
plugs into LeRobot's config machinery like any other robot (`01` FR-SYS-014,
third-party plugin -- no fork). The only backend-specific field is `mjcf_path`, an
optional override that defaults to the WP-0C-03 v2 asset; a SIM backend needs no
port, CAN interface, or motor config, and declares none.

Importing this module imports the robot stack (LeRobot); it is product code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lerobot.robots.config import RobotConfig


@RobotConfig.register_subclass("bi_openarm_mujoco")
@dataclass(kw_only=True)
class BiOpenArmMujocoConfig(RobotConfig):
    """Configuration for the `BiOpenArmMujoco` backend.

    Attributes:
        id: Instance id, used by LeRobot for the calibration file name.
        mjcf_path: Optional MJCF asset override; None uses the WP-0C-03 v2 asset.
    """

    id: str | None = "bi_openarm_mujoco"
    mjcf_path: Path | None = None
