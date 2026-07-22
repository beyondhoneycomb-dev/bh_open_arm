"""The WP-2C-07 Cartesian keep-out is reused by identity, and stays live in Freedrive.

The mandated reuse (`02b` §4 WP-2D-04): the Cartesian virtual walls come from `sim.walls`,
never a second wall geom. This proves the reuse by object identity and by an AST scan that the
band defines no wall-geom type, then exercises the reused keep-out as a Freedrive detector — it
flags a pose penetrating the active walls, passes a clear pose, and refuses over inactive walls.
"""

from __future__ import annotations

import ast

import pytest

pytest.importorskip("mujoco")

import mujoco

import sim.walls
from backend.freedrive_walls import cartesian_walls
from backend.freedrive_walls.cartesian_walls import FreedriveCartesianWalls
from sim.walls import CellWallsInactiveError, CellWallToggle
from tests.wp2d04 import FREEDRIVE_PACKAGE_DIR
from tests.wp2d04._fixtures import committed_cell_path

# Wall-geom type names WP-2C-07 owns; the band must define none of its own.
_WALL_GEOM_TYPES = {"WallGeom", "WallScene", "WallShape"}

_HOME_KEYFRAME = 0


def _cell_model() -> mujoco.MjModel:
    return mujoco.MjModel.from_xml_path(str(committed_cell_path()))


def _zeros_state(model: mujoco.MjModel) -> mujoco.MjData:
    data = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    mujoco.mj_forward(model, data)
    return data


def _home_state(model: mujoco.MjModel) -> mujoco.MjData:
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, _HOME_KEYFRAME)
    mujoco.mj_forward(model, data)
    return data


def test_reuses_sim_walls_by_identity() -> None:
    """The band's Cartesian check and toggle are the very WP-2C-07 objects, not copies."""
    assert cartesian_walls.guarded_cell_collision is sim.walls.guarded_cell_collision
    assert cartesian_walls.CellWallToggle is sim.walls.CellWallToggle
    assert cartesian_walls.CellWallsInactiveError is sim.walls.CellWallsInactiveError


def test_band_defines_no_second_wall_geom() -> None:
    """No module under the band declares a wall-geom type — WP-2C-07 owns the only one."""
    defined: set[str] = set()
    for source in FREEDRIVE_PACKAGE_DIR.glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        defined |= {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    assert defined.isdisjoint(_WALL_GEOM_TYPES)


def test_keep_out_flags_a_penetrating_pose_with_walls_active() -> None:
    """With the walls active, a pose penetrating them flags the reused keep-out."""
    model = _cell_model()
    toggle = CellWallToggle(model, enabled=True)
    walls = FreedriveCartesianWalls(model, _zeros_state(model), toggle)
    assert walls.check()


def test_keep_out_passes_a_clear_pose() -> None:
    """The collision-free home pose flags nothing."""
    model = _cell_model()
    toggle = CellWallToggle(model, enabled=True)
    walls = FreedriveCartesianWalls(model, _home_state(model), toggle)
    assert walls.check() == ()


def test_keep_out_refuses_over_inactive_walls() -> None:
    """A check over deactivated walls is refused, never a vacuous pass (WP-2C-07 ①)."""
    model = _cell_model()
    toggle = CellWallToggle(model, enabled=False)
    walls = FreedriveCartesianWalls(model, _zeros_state(model), toggle)
    with pytest.raises(CellWallsInactiveError):
        walls.check()
