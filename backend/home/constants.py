"""Home-profile constants (WP-2D-07): the adopted home and the hardstop it is not.

`FR-MAN-047` was `[결정필요]` because two poses were both called "home": the
`openarm_driver`/`openarm_mujoco` pose `[0, 0, 0, π/2, 0, 0, 0, 0]` (elbow bent 90°)
and the MoveIt SRDF named state `home` (every joint 0). `J4`'s mechanical range is
`[0, 2.4435]`, so `J4 = 0` is the *lower hardstop*, not a rest pose. This package adopts
the plan-stated resolution — "do not use the hardstop as home" → `J4 = π/2` — and these
constants are the single place that adoption is written down (`04` §3.6).
"""

from __future__ import annotations

import math

# Re-exported (explicit `as`) so the home modules and tests read the joint count from one
# place; its home is `backend.safety_bringup.constants`.
from backend.safety_bringup.constants import ARM_JOINT_COUNT as ARM_JOINT_COUNT

# URDF per-arm layout: seven arm joints then the gripper, so q[8] is one arm's driver
# state and joint4 (the elbow) is index 3.
PROFILE_WIDTH = ARM_JOINT_COUNT + 1
GRIPPER_INDEX = ARM_JOINT_COUNT
J4_INDEX = 3

# The adopted home elbow angle. π/2 is the exact value; the driver writes 1.5707963 and
# the MJCF home keyframe 1.570796, both roundings of the same number (the FK preview and
# the committed keyframe agree to that precision, verified in tests).
HOME_J4_ANGLE_RAD = math.pi / 2.0

# The pose FR-MAN-047 rules out: J4 at its mechanical lower bound is a hardstop, and a
# home must never sit on a hardstop. Kept as a named constant so the "not this" is as
# explicit as the "this".
J4_LOWER_HARDSTOP_RAD = 0.0

DEFAULT_HOME_PROFILE_NAME = "default"
SESSION_STOP_PROFILE_NAME = "session_stop"

# `[0, 0, 0, π/2, 0, 0, 0, 0]`, applied identically to the left and right arms (`04` §3.6).
DEFAULT_HOME_Q_URDF = (0.0, 0.0, 0.0, HOME_J4_ANGLE_RAD, 0.0, 0.0, 0.0, 0.0)

# Hardstop-avoidance tolerance: an arm joint within this of a soft-limit bound counts as
# sitting on the hardstop and is refused as a home. The gripper is exempt — its closed
# position is its mechanical zero, an intended boundary, so it is checked inclusively.
LIMIT_INTERIOR_EPS_RAD = 1e-9

# Waypoint-density auto-computation for the pre-verify trajectory (WP-2C-08 ② rule).
# The generated per-step joint delta is held below the geometry's density bound by this
# safety factor, so the reused collision preflight never refuses on sparsity.
HOME_DENSITY_SAFETY = 1.5
HOME_TRAJECTORY_MIN_WAYPOINTS = 2
HOME_TRAJECTORY_MAX_WAYPOINTS = 5000

# The deferred operator confirmation reads real observations from this directory when set;
# absent, the J4=0-hardstop visual confirm stays SKIP-with-reason (never asserted PASS).
HARDSTOP_FIXTURE_ENV_VAR = "OPENARM_HOME_HARDSTOP_FIXTURE"
