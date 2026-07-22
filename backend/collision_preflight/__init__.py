"""Collision preflight (WP-2C-08): a pre-send check over a waypoint trajectory.

The preflight drives each waypoint's `qpos` through `mj_forward` on the committed bimanual
MJCF and reports the first waypoint that puts two collision geoms within the safety margin,
with the offending geoms, their separation, the contact point, and the contact frame. It is
independent of IK (an IK solution carries no collision guarantee), gates itself on three
single-source rules — the `WP-1-06` margin policy, a startup proof that the arm-arm pair
test is live, and the waypoint-density rule that stands in for the dropped CCD — and refuses
rather than passes when any of them fails.

Reuse, not reimplementation: the link7 coverage check, the margin policy, and the MJCF path
locator are `WP-1-06`'s (`backend.safety_bringup`); the four deployment targets are
`targets.matrix`'s. This package adds the `mj_forward` walk, the density rule, the
self-collision activation proof, and the per-target latency bench whose target numbers are
deferred to on-target re-verification.
"""

from __future__ import annotations

from backend.collision_preflight.density import (
    DensityAssessment,
    DensityInsufficientError,
    assess_density,
    require_sufficient_density,
)
from backend.collision_preflight.link7 import (
    Link7Verification,
    inject_approx_cylinder_variant,
    materialize_link7_urdf,
    verify_link7_both,
)
from backend.collision_preflight.model import GeometryExtents, PreflightModel, geom_arm_side
from backend.collision_preflight.preflight import (
    ContactReport,
    PreflightResult,
    WaypointViolation,
    run_preflight,
)
from backend.collision_preflight.selfcollision import (
    SelfCollisionActivation,
    SelfCollisionInactiveError,
    assert_self_collision_active,
)

__all__ = [
    "ContactReport",
    "DensityAssessment",
    "DensityInsufficientError",
    "GeometryExtents",
    "Link7Verification",
    "PreflightModel",
    "PreflightResult",
    "SelfCollisionActivation",
    "SelfCollisionInactiveError",
    "WaypointViolation",
    "assert_self_collision_active",
    "assess_density",
    "geom_arm_side",
    "inject_approx_cylinder_variant",
    "materialize_link7_urdf",
    "require_sufficient_density",
    "run_preflight",
    "verify_link7_both",
]
