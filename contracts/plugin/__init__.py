"""CTR-PLUG@v1 — the OpenArm robot plugin contract (config + shared Robot ABC).

This package exposes two halves of the plugin contract:

- `contracts.plugin.config` — pure config types and their assembly-time validation
  (side required, follower/leader velocity-torque switch matched). It imports no
  robot stack and is re-exported here, so the acceptance fixtures run in the light
  lane.
- `contracts.plugin.robot_abc` — the shared LeRobot `Robot` ABC every backend
  implements (FR-SIM-097). It imports LeRobot, so it is NOT re-exported here;
  import it explicitly (`from contracts.plugin.robot_abc import OpenArmRobot`) to
  keep `import contracts.plugin` free of the robot stack.
"""

from __future__ import annotations

from contracts.plugin.config import (
    BimanualSessionConfig,
    ConfigError,
    FollowerConfig,
    LeaderConfig,
    Side,
    validate_teleop_pairing,
)

__all__ = [
    "BimanualSessionConfig",
    "ConfigError",
    "FollowerConfig",
    "LeaderConfig",
    "Side",
    "validate_teleop_pairing",
]
