"""The guarded cell-collision check: refuse when walls are inactive (WP-2C-07 ①).

Acceptance ①: running the cell-collision check with the walls off must be *refused*,
not answered with a clean result. The refusal itself is WP-2A-00's
`assert_cell_walls_active`, and the check itself is Wave 0-C's `check_cell_collision`;
this composes the two so the only supported way to run the check is one that cannot
return a vacuous green.

The composition also re-forwards the model after asserting the walls active. That step
is not cosmetic: `assert_cell_walls_active` reads the model's collision masks, but a
`data.contact` array computed while the walls were off holds no wall contacts, so a
check over stale contacts could pass with the masks now on — active model, empty
contacts, silent green. Forwarding after the assertion recomputes contacts under the
masks that were just verified, so the two agree. `02b` §1.2 WP-2C-07: walls inactive
but "check passed" is `FAIL_BLOCKING`, and this is where that would otherwise slip in.
"""

from __future__ import annotations

import mujoco

from backend.interlock.walls import assert_cell_walls_active
from sim.dryrun.checks.cell_collision import check_cell_collision
from sim.dryrun.violation import Violation


def guarded_cell_collision(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    sim_t: float,
) -> tuple[Violation, ...]:
    """Run the cell-collision check only when the six walls are active (WP-2C-07 ①).

    Args:
        model: The compiled model whose cell walls must be active — the toggle's model.
        data: The state to evaluate; its contacts are recomputed under the active masks.
        sim_t: Simulation time stamped onto each violation.

    Returns:
        (tuple[Violation, ...]) The Wave 0-C cell-collision violations, over a scene
        whose walls are proven active.

    Raises:
        CellWallsInactiveError: If any cell wall is inactive — the check is refused
            rather than run vacuously (WP-2A-00, `02b` §1.2 WP-2C-07).
    """
    assert_cell_walls_active(model)
    mujoco.mj_forward(model, data)
    return check_cell_collision(model, data, sim_t)
