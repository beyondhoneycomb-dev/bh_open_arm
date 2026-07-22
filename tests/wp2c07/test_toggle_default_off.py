"""The runtime wall toggle: default off, activate/deactivate, table always active.

`02b` §1.2 WP-2C-07: the six cell walls are inactive by default at runtime, and the
table (`cell_table_col`) is active always (③). These exercise the toggle directly on
the committed cell model, whose walls ship active, proving the toggle — not the asset —
is what establishes the safe default.
"""

from __future__ import annotations

import mujoco
import pytest

from backend.interlock.walls import CELL_WALL_GEOMS, inactive_cell_walls
from sim.walls import CELL_TABLE_GEOM, CellTableInactiveError, CellWallToggle
from tests.wp2c07._fixtures import cell_model, geom_masks


def test_construction_defaults_walls_off() -> None:
    """Constructing a toggle over the (walls-active) asset flips the walls to off."""
    model = cell_model()
    assert inactive_cell_walls(model) == ()  # asset ships active
    toggle = CellWallToggle(model)
    assert not toggle.walls_active
    assert set(inactive_cell_walls(model)) == set(CELL_WALL_GEOMS)


def test_activate_then_deactivate_round_trips_the_walls() -> None:
    """Activate switches all six walls on; deactivate switches them all off again."""
    model = cell_model()
    toggle = CellWallToggle(model)
    toggle.activate()
    assert toggle.walls_active
    assert inactive_cell_walls(model) == ()
    toggle.deactivate()
    assert set(inactive_cell_walls(model)) == set(CELL_WALL_GEOMS)


def test_explicit_enabled_true_activates_at_construction() -> None:
    """The toggle can be constructed already-on when a caller opts in explicitly."""
    model = cell_model()
    toggle = CellWallToggle(model, enabled=True)
    assert toggle.walls_active


def test_activate_restores_asset_declared_masks() -> None:
    """Activation restores the cell asset's own collision masks, not a guess."""
    model = cell_model()
    original = {name: geom_masks(model, name) for name in CELL_WALL_GEOMS}
    toggle = CellWallToggle(model)  # deactivates
    toggle.activate()
    for name in CELL_WALL_GEOMS:
        assert geom_masks(model, name) == original[name]


def test_table_stays_active_through_every_toggle() -> None:
    """Acceptance ③: the table is never in the toggled set and stays active."""
    model = cell_model()
    toggle = CellWallToggle(model)
    assert CELL_TABLE_GEOM not in CELL_WALL_GEOMS
    assert toggle.table_active  # walls off
    toggle.activate()
    assert toggle.table_active
    toggle.deactivate()
    assert toggle.table_active


def test_toggle_refuses_a_model_whose_table_is_inactive() -> None:
    """A scene whose always-active table is off is refused, not silently accepted (③)."""
    model = cell_model()
    table_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, CELL_TABLE_GEOM)
    model.geom_contype[table_id] = 0
    model.geom_conaffinity[table_id] = 0
    with pytest.raises(CellTableInactiveError):
        CellWallToggle(model)
