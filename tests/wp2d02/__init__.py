"""WP-2D-02 acceptance suite — singularity monitor + elbow nullspace over the reused jog.

Shared paths and helpers. The sim stack (mujoco/mink/openarm_control) and LeRobot are the
optional ``[robot]`` group, so every module here ``importorskip``s them. A near-singular
committed state (the right elbow driven toward straight) is the deterministic trigger for
the damping and hold paths; a jogged-off-home pose is the start for the elbow swivel.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SINGULARITY_PACKAGE_DIR = REPO_ROOT / "backend" / "singularity"

__all__ = ["REPO_ROOT", "SINGULARITY_PACKAGE_DIR"]
