"""Named constants for the interpolator, pre-verify, and replay (WP-2D-06).

Every value here is either a plan-given default (`02b` WP-2D-06: 50 Hz x 2 s), a
profile's analytic peak-velocity factor, or a provenance label. The physical ceilings the
pre-verify enforces are NOT redeclared here — the per-joint velocity canon is
`backend.safety_bringup.velocity.bootstrap_limiter_rad_s`, the position limits are
`sim.ik.arm_soft_limits`, and the density step ceiling is `WP-2C-08`'s geometry — so a
change to any of those moves this band with it rather than drifting from a second copy.
"""

from __future__ import annotations

# The plan defaults (`02b` WP-2D-06): the interpolation grid is 50 Hz and a segment between
# two waypoints is planned to take two seconds before any velocity-scale extension.
DEFAULT_RATE_HZ = 50.0
DEFAULT_SEGMENT_DURATION_S = 2.0

# A segment needs at least a start and an end sample; a one-sample "segment" has no motion
# to interpolate and no step to bound.
MIN_SAMPLES_PER_SEGMENT = 2

# Velocity scale is the fraction of the per-joint velocity ceiling a motion may use. Full
# scale (1.0) plans at the ceiling; a smaller scale slows the motion, which auto-extends the
# duration (`02b` WP-2D-06 ②). The floor keeps a scale from collapsing the duration formula.
FULL_VELOCITY_SCALE = 1.0
MIN_VELOCITY_SCALE = 0.01

# The analytic peak-velocity factor of each interpolation profile: the ratio of a segment's
# peak joint velocity to its mean velocity (displacement / duration). Linear holds mean
# velocity throughout (factor 1). Cubic smoothstep s(u)=3u^2-2u^3 peaks at u=0.5 with
# s'(0.5)=1.5. Quintic s(u)=10u^3-15u^4+6u^5 peaks at u=0.5 with s'(0.5)=1.875. The
# auto-extension multiplies mean velocity by this factor so the *peak* stays under the
# ceiling, and the discrete finite-difference velocity never exceeds that peak.
LINEAR_PEAK_FACTOR = 1.0
CUBIC_PEAK_FACTOR = 1.5
QUINTIC_PEAK_FACTOR = 1.875

# The per-step joint delta is held strictly below the `WP-2C-08` density ceiling with this
# margin so the reused collision density gate (which requires a strict `<`) is not tripped by
# a boundary-equal step. The auto-extension targets `ceiling * fraction`, never the ceiling.
DENSITY_TARGET_FRACTION = 0.9

# Numerical slack for the position-limit comparison, radians. A committed teaching point may
# sit exactly on a soft limit; a bare `<`/`>` would then read floating-point noise as a
# violation. Mirrors the `WP-2D-01` mechanical-limit tolerance so the two bands agree.
LIMIT_TOLERANCE_RAD = 1e-6

# The `02b` WP-2D-06 ④ UI note. v2.0 declares `has_acceleration_limits: false` for every
# joint, so nothing bounds the velocity step a linear profile takes at each waypoint, and
# that discontinuity pollutes the tracking residual. The note is shown whenever the linear
# profile is selected; it is a fact about the profile, not a runtime warning.
LINEAR_RESIDUAL_UI_NOTE = (
    "Linear interpolation holds a constant joint velocity within each segment and steps "
    "that velocity discontinuously at every waypoint. The v2.0 joint model declares "
    "has_acceleration_limits: false for every joint, so nothing bounds that step and the "
    "discontinuity pollutes the tracking residual. Prefer cubic or quintic when residual "
    "quality matters."
)
