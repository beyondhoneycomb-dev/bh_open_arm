"""Cell-wall activation as a precondition the interlock trusts before it gates.

The dry-run's cell-collision check (`sim.dryrun.checks.cell_collision`, Wave 0-C)
reads ``data.contact`` and reports robot-vs-cell penetrations. A wall geom with
``contype=0; conaffinity=0`` participates in no contact at all, so the check runs,
finds nothing, and returns a *clean* result over a scene whose walls were switched
off — a green that means "not checked", not "safe". WP-2C-07 makes exactly that
deactivation the runtime default for the six cell walls (the table stays active),
so the failure mode is not hypothetical.

This module is the interlock's guard against that vacuous green: it refuses to let
a dry-run verdict authorise real transmission unless the six cell-wall geoms are
collision-active on the very model the checks ran over. It classifies a wall as
active only when both ``contype`` and ``conaffinity`` are non-zero, because either
being zero removes the wall from the collision system. A wall geom missing from the
model is treated as inactive too: a check that cannot even resolve its wall cannot
be trusted to have run.
"""

from __future__ import annotations

import mujoco

# The six cell-boundary collision geoms of the WP-0C-03 cell asset (`sim/mjcf/v2/
# cell.xml`). The table (`cell_table_col`) is deliberately excluded: WP-2C-07 keeps
# it always-active and toggles only these six, so "the six walls" the plan names
# (`02b` §1.2 WP-2A-00 ③, WP-2C-07) are exactly this set.
CELL_WALL_GEOMS: tuple[str, ...] = (
    "cell_left_wall_col",
    "cell_right_wall_col",
    "cell_front_wall_col",
    "cell_roof_col",
    "cell_rail_col1",
    "cell_rail_col2",
)


class CellWallsInactiveError(RuntimeError):
    """Raised when a cell wall is collision-inactive, so cell-collision is vacuous.

    `02b` §1.2 WP-2A-00 ③: without the six wall geoms' ``contype``/``conaffinity``
    active, the cell-collision check cannot run meaningfully, and a verdict built on
    it must not authorise real transmission.
    """


def _geom_is_active(model: mujoco.MjModel, name: str) -> bool:
    """Whether a named geom is present and collision-active (both masks non-zero)."""
    geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name)
    if geom_id < 0:
        return False
    return int(model.geom_contype[geom_id]) != 0 and int(model.geom_conaffinity[geom_id]) != 0


def inactive_cell_walls(model: mujoco.MjModel) -> tuple[str, ...]:
    """Return the cell-wall geoms that are absent or collision-inactive.

    Args:
        model: The compiled model the dry-run resolves its cell-collision check over.

    Returns:
        (tuple[str, ...]) The wall geom names that are missing or have a zero
        ``contype``/``conaffinity``; empty when all six walls are active.
    """
    return tuple(name for name in CELL_WALL_GEOMS if not _geom_is_active(model, name))


def assert_cell_walls_active(model: mujoco.MjModel) -> None:
    """Refuse a model whose cell walls are not all collision-active (③).

    Args:
        model: The compiled model the dry-run's cell-collision check reads.

    Raises:
        CellWallsInactiveError: If any of the six cell walls is absent or has a zero
            ``contype``/``conaffinity`` — the cell-collision check would be vacuous.
    """
    inactive = inactive_cell_walls(model)
    if inactive:
        raise CellWallsInactiveError(
            "cell-collision check would run vacuously: the wall geoms "
            f"{list(inactive)} are absent or have contype/conaffinity=0; refusing to "
            "let this dry-run gate real transmission (02b §1.2 WP-2A-00 ③)"
        )
