"""WP-2D-01 acceptance suite — Cartesian jog adapter over the reused sim.ik solver.

Shared paths and helpers. The sim stack (mujoco/mink/openarm_control) and LeRobot are
the optional ``[robot]`` group, so every module here ``importorskip``s them. The
out-of-limit driver state is the deterministic trigger (borrowed from WP-0C-02) that
drives the reused adapter into its fault paths through the jog.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
JOG_PACKAGE_DIR = REPO_ROOT / "backend" / "cartesian_jog"

__all__ = ["JOG_PACKAGE_DIR", "REPO_ROOT"]
