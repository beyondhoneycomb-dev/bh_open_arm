"""Named parameters of the teleop safety gate (`WP-3B-10`).

Every threshold the gate's safety logic keys on is named here with its spec source,
so a reviewer can find the one place a value is decided and the negative branch a
value change would trip. Values the specification fixes (the 100 ms heartbeat, the
`1e-6` determinant tolerance, `treat_stale_as_lost`) are marked as frozen; values
the specification leaves open (the EE velocity ceilings, the link-loss deceleration)
carry a documented reference default and are runtime-tunable, following the same
"conservative default, active now" stance the WP-2A-04 velocity limiter takes.
"""

from __future__ import annotations

NANOS_PER_SECOND = 1_000_000_000
MILLIS_PER_SECOND = 1_000

# The VR link heartbeat timeout. `FR-TEL-081` fixes the default at 100 ms with a
# tunable range of 30–500 ms (`05` §5 parameter table). No fresh, OK-validity frame
# within this window on the server clock is a lost link.
DEFAULT_HEARTBEAT_TIMEOUT_MS = 100
MIN_HEARTBEAT_TIMEOUT_MS = 30
MAX_HEARTBEAT_TIMEOUT_MS = 500

# `treat_stale_as_lost` is frozen true (`FR-TEL-081`, `WP-3B-10` contract): tracking
# STALE(1) is indistinguishable downstream from a normal stop, so it is treated as a
# lost link, not a tolerated degraded state.
TREAT_STALE_AS_LOST = True

# Pose-sanity determinant tolerance. `FR-TEL-038`: a rotation matrix whose
# determinant is within this of zero (or any non-finite element) is a degenerate
# frame and the pose is discarded, the previous valid pose retained.
ROTATION_DET_ABS_TOL = 1e-6

# EE cartesian velocity ceilings. `FR-TEL-037` fixes the mechanism but not the value
# (`05` §5 Q-4 is open pending a measured hand-speed p99); the documented reference
# is the Pilz industrial default, adopted as the conservative active default and
# adjustable at runtime from the GUI.
DEFAULT_MAX_LINEAR_VEL_M_S = 1.0
DEFAULT_MAX_ANGULAR_VEL_RAD_S = 1.57

# Link-loss deceleration. `FR-TEL-081`/S5 mandate "decelerate then hold" on a lost
# link but fix no rate; this is the safety-gate tunable that ramps the coasting EE
# linear velocity to zero before the hold. Chosen so a 1 m/s command stops within a
# few centimetres of coast.
DEFAULT_LINK_LOST_DECEL_M_S2 = 4.0

# Consecutive workspace-wall violations tolerated as projection before the gate
# escalates to a fault hold. `FR-TEL` §4.3: a wall violation projects onto the
# boundary and stays following, but a *persistent* violation holds (S4 → S7).
DEFAULT_PERSISTENT_WALL_VIOLATION_TICKS = 10

# RID9 = 0 is not a period, it is the Damiao "HW comm-loss fallback disabled" flag
# (`PG-RID-001` negative branch, `WP-3B-10`): with no motor-side timeout the loop
# period cannot under-run it, so the startup check reports the disabled fallback
# rather than a pass/fail on timing.
RID9_HW_FALLBACK_DISABLED_SENTINEL = 0.0


def heartbeat_timeout_ns(timeout_ms: int) -> int:
    """Convert a heartbeat timeout in milliseconds to server-clock nanoseconds.

    Args:
        timeout_ms: The timeout in milliseconds; must be in the tunable range.

    Returns:
        (int) The timeout in nanoseconds.

    Raises:
        ValueError: If the timeout is outside the `FR-TEL-081` tunable range.
    """
    if not MIN_HEARTBEAT_TIMEOUT_MS <= timeout_ms <= MAX_HEARTBEAT_TIMEOUT_MS:
        raise ValueError(
            f"heartbeat timeout {timeout_ms} ms is outside the tunable range "
            f"[{MIN_HEARTBEAT_TIMEOUT_MS}, {MAX_HEARTBEAT_TIMEOUT_MS}] (FR-TEL-081)"
        )
    return timeout_ms * (NANOS_PER_SECOND // MILLIS_PER_SECOND)
