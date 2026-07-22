"""WP-1-06 — the extended safety bring-up, after the guarded torque-ON of WP-1-05.

`12` FR-SAF-069 makes this extension precede the gravity/friction compensation: without it
the GMO output has nowhere to go. The offline half lives here — everything that is a static
asset check or an arithmetic derivation, which RUNS on this host and must genuinely pass:

  * link7 collision coverage over the committed MJCF (READ, never written), the collision
    margin policy, and the virtual-wall / link7 injection into this WP's own `sim/safety`
    tree (`collision`).
  * the per-joint collision-threshold floor (ten torque LSBs, physics-owned) and the
    labelled +-10%-of-effort default (`thresholds`).
  * the detection method selector, its acceleration-limit precondition, the octomap
    deprecation scan, the friction/GMO gate, and the teleop no-pre-check notice
    (`detection`).
  * the PG-VEL-001 velocity canon — the three-way register/catalogue/URDF minimum, the
    proof the register is never canon, the bootstrap limiter, the default-active flip, and
    the self-approval refusal (`velocity`).
  * the sweep publication gate — three constraints or no artifact (`sweep`).
  * the detection-loop bandwidth verdict over WP-1-04's provisional f_max (`band`).

The hardware half — the command-following sweep under the bootstrap limiter — is deferred
to a real fixture and re-run by `reverify.reverify_from_fixture`; it is never asserted green
here, because a faked sweep pass is a safety lie about a brakeless 40 Nm arm.
"""

from __future__ import annotations

from backend.safety_bringup.band import (
    STALE_ON,
    DetectionBand,
    FramePattern,
    resolve_detection_band,
)
from backend.safety_bringup.collision import (
    Link7CollisionMissingError,
    MarginConfirmationRequiredError,
    MarginResolution,
    assert_link7_collision_in_mjcf,
    assert_link7_collision_in_urdf,
    committed_mjcf_path,
    count_virtual_wall_geoms,
    inject_link7_collision_urdf,
    inject_virtual_walls,
    resolve_collision_margin,
)
from backend.safety_bringup.detection import (
    DEFAULT_DETECTION_METHOD,
    DetectionMethod,
    OctomapReference,
    ResidualDetectionRefusedError,
    assert_teleop_notice_present,
    enable_residual_detection,
    gmo_active_default,
    scan_octomap_symbols,
    teleop_precheck_notice,
)
from backend.safety_bringup.preconditions import (
    ExtendedSafetyPreconditionError,
    assert_extended_safety_preconditions,
)
from backend.safety_bringup.reverify import (
    RealSweepVerification,
    fixture_dir_from_env,
    reverify_from_fixture,
)
from backend.safety_bringup.sweep import (
    SweepConstraints,
    SweepPublication,
    SweepPublicationRefusedError,
    SweepSample,
    assert_sweep_publishable,
)
from backend.safety_bringup.thresholds import (
    DefaultCollisionThresholds,
    ThresholdBelowFloorError,
    assert_threshold_above_floor,
    default_collision_thresholds,
    floor_for_joint,
    floor_for_motor,
)
from backend.safety_bringup.velocity import (
    DerivationSelfApprovalError,
    ThreeWayRow,
    VelocityLimiterDefault,
    VelocitySource,
    assert_derivation_basis_not_self,
    assert_register_never_canon,
    assert_velocity_limit_active_by_default,
    bootstrap_limiter_rad_s,
    physical_canon_rad_s,
    three_way_table,
    velocity_limiter_default,
)

__all__ = [
    "DEFAULT_DETECTION_METHOD",
    "STALE_ON",
    "DefaultCollisionThresholds",
    "DerivationSelfApprovalError",
    "DetectionBand",
    "DetectionMethod",
    "ExtendedSafetyPreconditionError",
    "FramePattern",
    "Link7CollisionMissingError",
    "MarginConfirmationRequiredError",
    "MarginResolution",
    "OctomapReference",
    "RealSweepVerification",
    "ResidualDetectionRefusedError",
    "SweepConstraints",
    "SweepPublication",
    "SweepPublicationRefusedError",
    "SweepSample",
    "ThreeWayRow",
    "ThresholdBelowFloorError",
    "VelocityLimiterDefault",
    "VelocitySource",
    "assert_derivation_basis_not_self",
    "assert_extended_safety_preconditions",
    "assert_link7_collision_in_mjcf",
    "assert_link7_collision_in_urdf",
    "assert_register_never_canon",
    "assert_sweep_publishable",
    "assert_teleop_notice_present",
    "assert_threshold_above_floor",
    "assert_velocity_limit_active_by_default",
    "bootstrap_limiter_rad_s",
    "committed_mjcf_path",
    "count_virtual_wall_geoms",
    "default_collision_thresholds",
    "enable_residual_detection",
    "fixture_dir_from_env",
    "floor_for_joint",
    "floor_for_motor",
    "gmo_active_default",
    "inject_link7_collision_urdf",
    "inject_virtual_walls",
    "physical_canon_rad_s",
    "resolve_collision_margin",
    "resolve_detection_band",
    "reverify_from_fixture",
    "scan_octomap_symbols",
    "teleop_precheck_notice",
    "three_way_table",
    "velocity_limiter_default",
]
