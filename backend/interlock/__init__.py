"""WP-2A-00 — the dry-run hard-gate interlock (B-2D.0 barrier).

The single gate standing in front of real transmission for both Wave 2D manual
motion and Wave 3C teleop real-send. It owns *only* the hard block: it consumes the
Wave 0-C dry-run report and forbids a REAL transition until that report passes. The
six checks, the report schema, and the ``TransmissionGrant`` token all belong to
``sim.dryrun`` and are reused here, never reimplemented.
"""

from __future__ import annotations

from backend.interlock.barrier import RealSendBarrier
from backend.interlock.decision import (
    InterlockDecision,
    InterlockState,
    RealTransitionBlockedError,
)
from backend.interlock.staticcheck import find_grant_fabrication
from backend.interlock.walls import (
    CELL_WALL_GEOMS,
    CellWallsInactiveError,
    assert_cell_walls_active,
    inactive_cell_walls,
)

__all__ = [
    "CELL_WALL_GEOMS",
    "CellWallsInactiveError",
    "InterlockDecision",
    "InterlockState",
    "RealSendBarrier",
    "RealTransitionBlockedError",
    "assert_cell_walls_active",
    "find_grant_fabrication",
    "inactive_cell_walls",
]
