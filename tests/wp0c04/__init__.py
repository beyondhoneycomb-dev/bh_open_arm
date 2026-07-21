"""WP-0C-04 acceptance suite — FK<->IK round-trip regression.

Shared paths and the fixture corpus for the index static check. The sim stack
(mujoco/mink/openarm_control) and LeRobot are the optional ``[robot]`` group, so
every module here ``importorskip``s them before importing ``sim.fkik``.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
HARDCODED_INDEX_FIXTURE = FIXTURES_DIR / "hardcoded_index.py.txt"
NAME_RESOLVED_FIXTURE = FIXTURES_DIR / "name_resolved.py.txt"

__all__ = [
    "FIXTURES_DIR",
    "HARDCODED_INDEX_FIXTURE",
    "NAME_RESOLVED_FIXTURE",
    "REPO_ROOT",
]
