"""WP-0C-02 acceptance suite — IK adapter, jnt_range override, fallback control.

Shared paths and the small IK-params tuning the acceptance tests build adapters
with. The sim stack (mujoco/mink/openarm_control) and LeRobot are the optional
``[robot]`` group, so every module here ``importorskip``s them.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
ORDER_VIOLATION_FIXTURE = FIXTURES_DIR / "kinematics_direct.py.txt"

__all__ = ["FIXTURES_DIR", "ORDER_VIOLATION_FIXTURE", "REPO_ROOT"]
