"""The committed bimanual model loaded for collision preflight, with margin and geometry.

`WP-2C-08` reads the `WP-0C-03` bimanual MJCF (never writes it) and drives it through
`mj_forward` per waypoint (`02b` WP-2C-08). This module owns the in-memory model: it loads
the committed asset through the `WP-1-06` locator (one path canon), applies a uniform
collision margin to every collision geom so `mj_forward` surfaces within-buffer proximity
and not only hard penetration, and exposes the geometry the waypoint-density rule needs.

Ownership / threading: `PreflightModel` holds one `mujoco.MjModel` and one `mujoco.MjData`
and mutates that data on every `forward` call, so a single instance is not safe to share
across threads. Load one per preflight run.

The margin is `WP-1-06`'s policy, not a second one: the caller resolves a requested margin
through `backend.safety_bringup.collision.resolve_collision_margin` and hands the honoured
value here, so the >=0.02 m default and the zero-margin confirmation live in exactly one
place (`12` FR-SAF-011).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import mujoco
import numpy as np

from backend.collision_preflight.constants import (
    ARM_LEFT_NAME_TOKEN,
    ARM_RIGHT_NAME_TOKEN,
    COLLISION_GEOM_NAME_TOKEN,
)
from backend.safety_bringup.collision import committed_mjcf_path
from backend.safety_bringup.constants import ARM_JOINT_COUNT


@dataclass(frozen=True)
class GeometryExtents:
    """The link-geometry extents the waypoint-density rule reads (`02b` WP-2C-08 ②).

    Attributes:
        max_link_radius_m: The largest collision-geom bounding radius, metres — the lever
            arm converting a joint step to a Cartesian sweep.
        min_link_thickness_m: The thinnest collision-geom dimension, metres — twice the
            smallest axis-aligned half-extent over the collision geoms; the smallest gap a
            link could tunnel through between two waypoints.
    """

    max_link_radius_m: float
    min_link_thickness_m: float


def geom_arm_side(name: str) -> str:
    """Return which arm a geom belongs to from its name, or "" for neither.

    Args:
        name: The geom name.

    Returns:
        (str) "left", "right", or "" when the geom is on neither arm.
    """
    if ARM_LEFT_NAME_TOKEN in name:
        return "left"
    if ARM_RIGHT_NAME_TOKEN in name:
        return "right"
    return ""


class PreflightModel:
    """The committed bimanual model, margin-inflated, ready for per-waypoint `mj_forward`.

    Ownership: holds and mutates one `MjData`; not thread-safe. The MJCF is READ from the
    `WP-0C-03` asset and never written.
    """

    def __init__(self, margin_m: float) -> None:
        """Load the committed bimanual MJCF and inflate every collision geom's margin.

        Args:
            margin_m: The honoured collision margin in metres (already resolved through the
                `WP-1-06` margin policy). Every collision geom's margin is set to it, so a
                contact is generated whenever two geoms are within this buffer, not only on
                penetration.
        """
        self._margin_m = margin_m
        self._model = mujoco.MjModel.from_xml_path(str(committed_mjcf_path()))
        self._data = mujoco.MjData(self._model)
        self._collision_geoms = self._find_collision_geoms()
        for geom_id in self._collision_geoms:
            self._model.geom_margin[geom_id] = margin_m

    @property
    def margin_m(self) -> float:
        """The collision margin applied to every collision geom, metres."""
        return self._margin_m

    @property
    def nq(self) -> int:
        """The model's generalized-coordinate count (both arms plus fingers)."""
        return int(self._model.nq)

    @property
    def collision_geom_ids(self) -> tuple[int, ...]:
        """The geom ids that participate in collision checking."""
        return self._collision_geoms

    def qpos_from_arms(self, left: Sequence[float], right: Sequence[float]) -> tuple[float, ...]:
        """Build a full-model configuration from two seven-joint arm vectors (fingers zero).

        Joints are addressed by name (`openarm_<side>_joint<1..7>`) rather than by a fixed
        qpos layout, so the mapping survives a re-ordering of the asset's coordinates.

        Args:
            left: The left arm's seven joint angles, joint1..joint7, radians.
            right: The right arm's seven joint angles, joint1..joint7, radians.

        Returns:
            (tuple[float, ...]) A configuration of length `nq`, arm joints set and every
            other coordinate (fingers) left at zero.

        Raises:
            ValueError: If either arm vector is not length seven.
        """
        if len(left) != ARM_JOINT_COUNT or len(right) != ARM_JOINT_COUNT:
            raise ValueError(
                f"each arm vector must hold {ARM_JOINT_COUNT} joints; "
                f"got left={len(left)}, right={len(right)}"
            )
        qpos = [0.0] * self.nq
        for side, vector in (("left", left), ("right", right)):
            for index in range(ARM_JOINT_COUNT):
                joint_name = f"openarm_{side}_joint{index + 1}"
                joint_id = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
                if joint_id < 0:
                    raise ValueError(f"model declares no joint {joint_name!r}")
                qpos[int(self._model.jnt_qposadr[joint_id])] = float(vector[index])
        return tuple(qpos)

    def random_configuration(self, rng: np.random.Generator) -> tuple[float, ...]:
        """Sample a configuration uniformly within every bounded joint's range.

        Args:
            rng: The random generator; a seeded one makes the sample reproducible.

        Returns:
            (tuple[float, ...]) A configuration of length `nq`.
        """
        qpos = [0.0] * self.nq
        for joint_id in range(int(self._model.njnt)):
            low = float(self._model.jnt_range[joint_id][0])
            high = float(self._model.jnt_range[joint_id][1])
            if low < high:
                address = int(self._model.jnt_qposadr[joint_id])
                qpos[address] = float(rng.uniform(low, high))
        return tuple(qpos)

    def geom_name(self, geom_id: int) -> str:
        """Return a geom's name, or its id as text when it is unnamed.

        Args:
            geom_id: The geom id.

        Returns:
            (str) The geom name.
        """
        name = mujoco.mj_id2name(self._model, mujoco.mjtObj.mjOBJ_GEOM, geom_id)
        return name if name is not None else str(geom_id)

    def geom_contype_conaffinity(self, geom_id: int) -> tuple[int, int]:
        """Return a geom's `(contype, conaffinity)` bitmask pair.

        Args:
            geom_id: The geom id.

        Returns:
            (tuple[int, int]) The contype and conaffinity bitmasks.
        """
        return int(self._model.geom_contype[geom_id]), int(self._model.geom_conaffinity[geom_id])

    def forward(self, qpos: Sequence[float]) -> mujoco.MjData:
        """Set the configuration and run `mj_forward`, returning the populated data.

        Args:
            qpos: A full-model configuration of length `nq`.

        Returns:
            (mujoco.MjData) The model data after the forward pass; `ncon` and `contact[]`
            are populated. The returned object is this model's own mutable data, valid
            until the next `forward`.

        Raises:
            ValueError: If `qpos` is not length `nq`.
        """
        if len(qpos) != self.nq:
            raise ValueError(f"qpos has length {len(qpos)}, expected nq={self.nq}")
        self._data.qpos[:] = np.asarray(qpos, dtype=float)
        mujoco.mj_forward(self._model, self._data)
        return self._data

    def geometry_extents(self) -> GeometryExtents:
        """Compute the link-radius and link-thickness extents over the collision geoms (②).

        Returns:
            (GeometryExtents) The max collision-geom bounding radius and the thinnest
            collision-geom dimension.

        Raises:
            ValueError: If the model declares no collision geoms.
        """
        if not self._collision_geoms:
            raise ValueError("model declares no collision geoms; extents are undefined")
        aabb = np.asarray(self._model.geom_aabb, dtype=float).reshape(-1, 6)
        max_radius = 0.0
        min_thickness = float("inf")
        for geom_id in self._collision_geoms:
            max_radius = max(max_radius, float(self._model.geom_rbound[geom_id]))
            half_extents = aabb[geom_id, 3:6]
            min_thickness = min(min_thickness, 2.0 * float(half_extents.min()))
        return GeometryExtents(max_link_radius_m=max_radius, min_link_thickness_m=min_thickness)

    def _find_collision_geoms(self) -> tuple[int, ...]:
        """Return the ids of every geom whose name marks it as a collision geom.

        Returns:
            (tuple[int, ...]) Collision geom ids in ascending order.
        """
        found: list[int] = []
        for geom_id in range(int(self._model.ngeom)):
            name = mujoco.mj_id2name(self._model, mujoco.mjtObj.mjOBJ_GEOM, geom_id) or ""
            if COLLISION_GEOM_NAME_TOKEN in name:
                found.append(geom_id)
        return tuple(found)
