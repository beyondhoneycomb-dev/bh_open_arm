"""Waypoint-density auto-computation — the CCD-absence compensation (`02b` WP-2C-08 ②).

Dropping MoveIt's Bullet continuous collision detection (`02b` §3.3) means the preflight
samples discrete waypoints and can tunnel a thin link straight through a thin obstacle
between two samples. The density rule bounds that risk without CCD: a joint step of `Δθ`
sweeps a point at radius `r` through an arc of about `r·Δθ`, so if the largest such sweep
between consecutive waypoints stays below the thinnest link dimension, no link can cross a
gap it would collide with. The plan fixes the exact inequality:

    max joint displacement per step  ×  max link radius  <  min link thickness

When it holds the sampling is dense enough; when it fails the verification is REFUSED, not
downgraded to a warning — a sparse trajectory that reports "no collision" is the silent
vacuous pass this rule exists to stop.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from backend.collision_preflight.model import GeometryExtents


@dataclass(frozen=True)
class DensityAssessment:
    """The verdict of the waypoint-density rule over one trajectory (`02b` WP-2C-08 ②).

    Attributes:
        max_joint_step_rad: The largest per-step joint displacement over the trajectory,
            radians; 0.0 for a trajectory of fewer than two waypoints.
        max_link_radius_m: The lever arm used, metres.
        min_link_thickness_m: The thinnest link dimension used, metres.
        swept_bound_m: `max_joint_step_rad · max_link_radius_m`, the sweep bound.
        required_max_step_rad: The largest step the geometry admits,
            `min_link_thickness_m / max_link_radius_m`.
        sufficient: True when `swept_bound_m < min_link_thickness_m`.
    """

    max_joint_step_rad: float
    max_link_radius_m: float
    min_link_thickness_m: float
    swept_bound_m: float
    required_max_step_rad: float
    sufficient: bool

    def as_record(self) -> dict[str, Any]:
        """Render the assessment for an evidence artifact.

        Returns:
            (dict[str, Any]) Every field of the assessment.
        """
        return {
            "max_joint_step_rad": self.max_joint_step_rad,
            "max_link_radius_m": self.max_link_radius_m,
            "min_link_thickness_m": self.min_link_thickness_m,
            "swept_bound_m": self.swept_bound_m,
            "required_max_step_rad": self.required_max_step_rad,
            "sufficient": self.sufficient,
        }


class DensityInsufficientError(Exception):
    """Raised when a trajectory is too sparse to check without CCD (`02b` WP-2C-08 ②).

    The verification is refused rather than run: between two waypoints spaced wider than
    the density bound a link can tunnel through a collision the discrete samples never see,
    so a "no collision" result would be vacuous.
    """


def max_joint_step_rad(trajectory: Sequence[Sequence[float]]) -> float:
    """Return the largest per-step joint displacement over a trajectory, radians.

    Args:
        trajectory: Waypoints, each a full-model configuration.

    Returns:
        (float) The maximum over consecutive-waypoint steps of the maximum over joints of
        the absolute joint change; 0.0 when there are fewer than two waypoints.
    """
    largest = 0.0
    for earlier, later in zip(trajectory, trajectory[1:], strict=False):
        for before, after in zip(earlier, later, strict=False):
            largest = max(largest, abs(after - before))
    return largest


def assess_density(
    trajectory: Sequence[Sequence[float]], extents: GeometryExtents
) -> DensityAssessment:
    """Compute the waypoint-density verdict for a trajectory (`02b` WP-2C-08 ②).

    Args:
        trajectory: Waypoints, each a full-model configuration.
        extents: The model's link-radius and link-thickness extents.

    Returns:
        (DensityAssessment) The step, the bound, the requirement, and whether the sampling
        is dense enough.
    """
    step = max_joint_step_rad(trajectory)
    swept = step * extents.max_link_radius_m
    required = (
        float("inf")
        if extents.max_link_radius_m == 0.0
        else extents.min_link_thickness_m / extents.max_link_radius_m
    )
    return DensityAssessment(
        max_joint_step_rad=step,
        max_link_radius_m=extents.max_link_radius_m,
        min_link_thickness_m=extents.min_link_thickness_m,
        swept_bound_m=swept,
        required_max_step_rad=required,
        sufficient=swept < extents.min_link_thickness_m,
    )


def require_sufficient_density(
    trajectory: Sequence[Sequence[float]], extents: GeometryExtents
) -> DensityAssessment:
    """Return the density assessment, refusing verification when the sampling is too sparse.

    Args:
        trajectory: Waypoints, each a full-model configuration.
        extents: The model's link-radius and link-thickness extents.

    Returns:
        (DensityAssessment) The assessment, always sufficient on return.

    Raises:
        DensityInsufficientError: When the density bound is not met (verification refused).
    """
    assessment = assess_density(trajectory, extents)
    if not assessment.sufficient:
        raise DensityInsufficientError(
            f"waypoint density insufficient: max step {assessment.max_joint_step_rad:.4f} rad "
            f"× max link radius {assessment.max_link_radius_m:.4f} m = "
            f"{assessment.swept_bound_m:.4f} m is not below min link thickness "
            f"{assessment.min_link_thickness_m:.4f} m; resample below "
            f"{assessment.required_max_step_rad:.4f} rad/step (02b WP-2C-08 ②)"
        )
    return assessment
