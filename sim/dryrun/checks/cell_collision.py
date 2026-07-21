"""Check ④ — cell collision (`09` FR-SIM-030 ④).

Reports every contact between a robot collision geom (geom group 3) and a cell
collision geom (geom group 4: walls, ceiling, rail, table) as one ``OA-DRY-004``
violation, the overage being the penetration depth in metres.

A MuJoCo contact carries a signed ``dist``: negative is interpenetration,
non-negative is a gap within the collision margin. Only true penetration past a
small tolerance is a collision — a contact grazing at ``dist ≈ 0`` is geometric
touching within numerical noise, not a strike — so the check keys on
``dist < -PENETRATION_TOLERANCE_M``. This module classifies contacts by the two
geoms' groups; it does not curate which geom pairs *should* collide (asset-level
exclusion pairs are WP-0C-03 / WP-2C-08 territory), so a genuine penetration in
the loaded asset is reported rather than hidden.
"""

from __future__ import annotations

import mujoco

from sim.dryrun.collision import (
    CELL_COLLISION_GROUP,
    PENETRATION_TOLERANCE_M,
    ROBOT_COLLISION_GROUP,
    iter_penetrations,
)
from sim.dryrun.violation import DryRunCheck, Violation


def check_cell_collision(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    sim_t: float,
) -> tuple[Violation, ...]:
    """Report robot-vs-cell penetrations in the forward-evaluated state.

    Args:
        model: The compiled model.
        data: The forward-evaluated state whose ``contact`` array is read.
        sim_t: Simulation time in seconds, stamped onto each violation.

    Returns:
        (tuple[Violation, ...]) One ``OA-DRY-004`` per robot-cell penetration.
    """
    violations: list[Violation] = []
    for penetration in iter_penetrations(model, data):
        groups = {penetration.group_a, penetration.group_b}
        if groups == {ROBOT_COLLISION_GROUP, CELL_COLLISION_GROUP}:
            violations.append(
                Violation(
                    item=DryRunCheck.CELL_COLLISION,
                    sim_t=sim_t,
                    joint=penetration.pair_label,
                    overage=penetration.depth_m,
                )
            )
    return tuple(violations)


# Re-exported so callers importing the check need not reach into `collision`.
__all__ = ["check_cell_collision", "PENETRATION_TOLERANCE_M"]
