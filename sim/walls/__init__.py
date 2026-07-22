"""WP-2C-07 — virtual walls: editable box/plane geoms plus the runtime wall toggle.

Two surfaces sit behind `12` FR-SAF-013 / FR-SIM-034 / FR-GUI-111 and `02b` §1.2
WP-2C-07, and this package owns exactly them:

  * The **runtime toggle** (`CellWallToggle`) for the six cell walls — off by default,
    activated before a cell-collision check may be trusted. The refusal it enforces is
    WP-2A-00's `assert_cell_walls_active`; `guarded_cell_collision` composes toggle and
    check so a walls-off run is refused, never a vacuous green. The table stays active.

  * The **editable virtual-wall scene** (`WallGeom` / `WallScene`) — define, edit, save,
    reload box/plane collision geoms in WP-1-06's own scene shape, the offline half of
    "3D edit and save". `seed_from_injector` starts that editing from the WP-1-06
    injector's walls rather than declaring a second set.

Reused, not rebuilt: `CELL_WALL_GEOMS` and the wall-active rule (WP-2A-00
`backend.interlock.walls`); the geom-injection scene shape and `MJCF_COLLISION_CLASS`
(WP-1-06 `backend.safety_bringup.collision`); `check_cell_collision` (Wave 0-C).
"""

from __future__ import annotations

from backend.interlock.walls import CellWallsInactiveError
from sim.walls.geoms import WallGeom, WallGeomError, WallShape
from sim.walls.guard import guarded_cell_collision
from sim.walls.scene import (
    DuplicateWallError,
    WallNotFoundError,
    WallScene,
    seed_from_injector,
)
from sim.walls.toggle import (
    CELL_TABLE_GEOM,
    DEFAULT_WALLS_ENABLED,
    CellTableInactiveError,
    CellWallToggle,
)

__all__ = [
    "CELL_TABLE_GEOM",
    "DEFAULT_WALLS_ENABLED",
    "CellTableInactiveError",
    "CellWallToggle",
    "CellWallsInactiveError",
    "DuplicateWallError",
    "WallGeom",
    "WallGeomError",
    "WallNotFoundError",
    "WallScene",
    "WallShape",
    "guarded_cell_collision",
    "seed_from_injector",
]
