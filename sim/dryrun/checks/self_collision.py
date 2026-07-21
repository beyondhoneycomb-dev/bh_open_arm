"""Check ⑤ — self-collision (`09` FR-SIM-030 ⑤).

Reports every contact between two robot collision geoms (both geom group 3) as one
``OA-DRY-005`` violation, the overage being the penetration depth in metres.

Keys on true penetration past the shared tolerance, exactly as the cell-collision
check does, so an arm's coupled gripper fingers touching at ``dist ≈ 0`` are not a
self-strike while a link driven into another link is. This module only classifies
group-3-vs-group-3 penetrations; which robot geom pairs are *allowed* to touch by
design (asset exclusion pairs) is curated by WP-0C-03 / WP-2C-08, so a genuine
self-penetration in the loaded asset is reported, never silently absorbed.
"""

from __future__ import annotations

import mujoco

from sim.dryrun.collision import ROBOT_COLLISION_GROUP, iter_penetrations
from sim.dryrun.violation import DryRunCheck, Violation


def check_self_collision(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    sim_t: float,
) -> tuple[Violation, ...]:
    """Report robot-vs-robot penetrations in the forward-evaluated state.

    Args:
        model: The compiled model.
        data: The forward-evaluated state whose ``contact`` array is read.
        sim_t: Simulation time in seconds, stamped onto each violation.

    Returns:
        (tuple[Violation, ...]) One ``OA-DRY-005`` per robot self-penetration.
    """
    violations: list[Violation] = []
    for penetration in iter_penetrations(model, data):
        if penetration.group_a == ROBOT_COLLISION_GROUP == penetration.group_b:
            violations.append(
                Violation(
                    item=DryRunCheck.SELF_COLLISION,
                    sim_t=sim_t,
                    joint=penetration.pair_label,
                    overage=penetration.depth_m,
                )
            )
    return tuple(violations)
