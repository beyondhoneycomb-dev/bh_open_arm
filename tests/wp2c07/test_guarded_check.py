"""Acceptance ① — the cell-collision check is refused while the walls are off.

`02b` §1.2 WP-2C-07 ①: running the cell-collision check without the walls active must
be refused. Walls-inactive but "check passed" is `FAIL_BLOCKING` (a silent disable), so
the guard must raise on the default-off toggle and only run once the walls are on — and
when it runs, it must genuinely evaluate (pass a clear pose, detect a penetrating one).
"""

from __future__ import annotations

import mujoco
import pytest

from sim.walls import CellWallsInactiveError, CellWallToggle, guarded_cell_collision
from tests.wp2c07._fixtures import cell_model, home_state, zeros_state


def test_guarded_check_refused_when_walls_off() -> None:
    """With the default-off toggle, the guarded check refuses rather than returns clean."""
    model = cell_model()
    data = home_state(model)
    CellWallToggle(model)  # default off
    with pytest.raises(CellWallsInactiveError):
        guarded_cell_collision(model, data, 0.0)


def test_guarded_check_refused_when_a_single_wall_off() -> None:
    """Any one inactive wall is enough to refuse — the check would be partial otherwise."""
    model = cell_model()
    data = home_state(model)
    toggle = CellWallToggle(model)
    toggle.activate()
    wall_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "cell_front_wall_col")
    model.geom_contype[wall_id] = 0
    model.geom_conaffinity[wall_id] = 0
    with pytest.raises(CellWallsInactiveError):
        guarded_cell_collision(model, data, 0.0)


def test_guarded_check_passes_a_clear_pose_with_walls_active() -> None:
    """Activated walls, home pose: the check runs and reports no penetration."""
    model = cell_model()
    data = home_state(model)
    CellWallToggle(model, enabled=True)
    violations = guarded_cell_collision(model, data, 0.0)
    assert violations == ()


def test_guarded_check_detects_a_penetrating_pose_with_walls_active() -> None:
    """Activated walls, all-zeros pose: the check runs and reports real penetrations."""
    model = cell_model()
    data = zeros_state(model)
    CellWallToggle(model, enabled=True)
    violations = guarded_cell_collision(model, data, 0.0)
    assert len(violations) > 0


def test_reforward_closes_the_stale_contact_gap() -> None:
    """Activating after a walls-off forward still detects: the guard re-forwards.

    A check over contacts computed while the walls were off would pass with the masks
    now on — active model, empty contacts, silent green. The guard forwards after
    asserting active, so the penetrating pose is caught even when the last forward the
    caller ran was before activation.
    """
    model = cell_model()
    data = zeros_state(model)  # forwarded with walls active-in-asset...
    toggle = CellWallToggle(model)  # ...but the toggle then switches them off
    assert not toggle.walls_active
    toggle.activate()
    violations = guarded_cell_collision(model, data, 0.0)
    assert len(violations) > 0
