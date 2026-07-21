"""WP-0C-01 acceptance suite -- MuJoCo backend on the LeRobot Robot ABC.

Shared source-tree locations, resolved from this file so the suite is independent
of the working directory. Kept import-light: the modules that need the robot stack
or `mujoco` `importorskip` it themselves.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_PKG_DIR = REPO_ROOT / "packages" / "lerobot_robot_openarm_mujoco"
SIM_MUJOCO_DIR = REPO_ROOT / "sim" / "mujoco"

__all__ = ["BACKEND_PKG_DIR", "REPO_ROOT", "SIM_MUJOCO_DIR"]
