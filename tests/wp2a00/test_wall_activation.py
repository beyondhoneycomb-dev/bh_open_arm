"""Acceptance ③ — the cell-collision check may not gate real-send with walls off.

A cell wall with ``contype=0; conaffinity=0`` takes part in no contact, so the
cell-collision check runs, finds nothing, and returns a *clean* result over a scene
whose walls were switched off — a vacuous green. The interlock refuses to trust such
a verdict: it verifies the six walls are collision-active on the exact model the
checks ran over, and hard-refuses otherwise, both as a unit check and end-to-end
through ``run_and_gate``.
"""

from __future__ import annotations

import mujoco
import pytest

from backend.interlock import (
    CELL_WALL_GEOMS,
    CellWallsInactiveError,
    RealSendBarrier,
    assert_cell_walls_active,
    inactive_cell_walls,
)
from sim.dryrun.runner import DryRunRunner, Waypoint
from tests.wp2a00._fixtures import CLEAN_POSE, cell_model, make_canon

_TABLE_GEOM = "cell_table_col"


def _deactivate(model: mujoco.MjModel, *names: str) -> None:
    """Switch the named geoms out of the collision system (contype/conaffinity = 0)."""
    for name in names:
        geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name)
        model.geom_contype[geom_id] = 0
        model.geom_conaffinity[geom_id] = 0


def test_pristine_cell_model_has_all_walls_active() -> None:
    """The committed cell asset ships with all six walls active — no false refusal."""
    model, _ = cell_model()
    assert inactive_cell_walls(model) == ()
    assert_cell_walls_active(model)  # does not raise


def test_all_walls_deactivated_is_refused() -> None:
    """With the six walls switched off, the interlock refuses the scene (③)."""
    model, _ = cell_model()
    _deactivate(model, *CELL_WALL_GEOMS)
    assert set(inactive_cell_walls(model)) == set(CELL_WALL_GEOMS)
    with pytest.raises(CellWallsInactiveError):
        assert_cell_walls_active(model)


def test_a_single_deactivated_wall_is_enough_to_refuse() -> None:
    """Any one inactive wall makes the cell-collision check untrustworthy — refuse."""
    model, _ = cell_model()
    _deactivate(model, "cell_front_wall_col")
    assert inactive_cell_walls(model) == ("cell_front_wall_col",)
    with pytest.raises(CellWallsInactiveError):
        assert_cell_walls_active(model)


def test_deactivating_walls_does_not_touch_the_always_active_table() -> None:
    """The table is excluded from the six walls; deactivating walls leaves it active."""
    model, _ = cell_model()
    _deactivate(model, *CELL_WALL_GEOMS)
    table_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, _TABLE_GEOM)
    assert int(model.geom_contype[table_id]) != 0
    assert int(model.geom_conaffinity[table_id]) != 0
    assert _TABLE_GEOM not in CELL_WALL_GEOMS


def test_run_and_gate_refuses_before_trusting_a_walls_off_verdict() -> None:
    """End-to-end: a runner whose walls are off is refused, not silently armed (③)."""
    barrier = RealSendBarrier()
    runner = DryRunRunner(make_canon())
    _deactivate(runner._model, *CELL_WALL_GEOMS)

    with pytest.raises(CellWallsInactiveError):
        barrier.run_and_gate(runner, [Waypoint(sim_t=0.0, positions_rad=CLEAN_POSE)])
    assert barrier.permits_real_send is False
