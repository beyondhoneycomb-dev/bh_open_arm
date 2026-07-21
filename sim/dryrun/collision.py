"""Shared contact classification for the two collision checks (④ and ⑤).

Both the cell-collision and self-collision checks read the same ``data.contact``
array and classify each contact by the geom-group convention `09` FR-SIM-030
fixes: robot collision geoms are group 3, cell collision geoms (walls, ceiling,
rail, table) are group 4. This module walks the contacts once and yields the true
penetrations with their two geom groups, so each check only has to match the pair
of groups it cares about. Keeping it here means the group constants and the
penetration threshold are defined once, not duplicated per check.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import mujoco

# `09` FR-SIM-030 geom-group convention.
ROBOT_COLLISION_GROUP = 3
CELL_COLLISION_GROUP = 4

# A contact penetrating by less than this (metres) is geometric touching within
# numerical noise, not a strike. Real penetrations in this asset are centimetres
# deep, so this margin separates grazing from collision without hiding any strike.
PENETRATION_TOLERANCE_M = 1e-4


@dataclass(frozen=True)
class Penetration:
    """One penetrating contact and the groups of its two geoms.

    Attributes:
        geom_a: Name of the first contacting geom (or its id as text if unnamed).
        geom_b: Name of the second contacting geom.
        group_a: Geom group of the first geom.
        group_b: Geom group of the second geom.
        depth_m: Penetration depth in metres (a positive magnitude).
    """

    geom_a: str
    geom_b: str
    group_a: int
    group_b: int
    depth_m: float

    @property
    def pair_label(self) -> str:
        """Return a stable ``geom_a<->geom_b`` label for the violation locus."""
        return f"{self.geom_a}<->{self.geom_b}"


def _geom_name(model: mujoco.MjModel, geom_id: int) -> str:
    """Return a geom's name, or its id as text when the geom is unnamed."""
    name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_id)
    return name if name else f"geom#{geom_id}"


def iter_penetrations(model: mujoco.MjModel, data: mujoco.MjData) -> Iterator[Penetration]:
    """Yield every contact penetrating past the tolerance, with geom groups.

    Args:
        model: The compiled model.
        data: The forward-evaluated state whose ``contact`` array is read.

    Yields:
        (Penetration) One record per penetrating contact.
    """
    for index in range(data.ncon):
        contact = data.contact[index]
        depth = -float(contact.dist)
        if depth <= PENETRATION_TOLERANCE_M:
            continue
        geom1 = int(contact.geom1)
        geom2 = int(contact.geom2)
        yield Penetration(
            geom_a=_geom_name(model, geom1),
            geom_b=_geom_name(model, geom2),
            group_a=int(model.geom_group[geom1]),
            group_b=int(model.geom_group[geom2]),
            depth_m=depth,
        )
