"""Named quantities for the Cartesian jog adapter (WP-2D-01).

Step sizes are jog increments, not safety limits: the safety envelope is the
`sim.ik` mechanical-limit clamp and (downstream) `backend.jogclamp`. The caps here
only stop a single jog command from requesting an absurd Cartesian delta before IK
ever runs. MJCF body/joint names are the model handles the frame resolver reads;
they are the v2 cell asset's names and change only if that asset does.
"""

from __future__ import annotations

import math

# Default jog increments. Translation in metres, rotation in radians. Runtime
# settable on the adapter; these are the power-on values a UI starts from.
DEFAULT_TRANSLATION_STEP_M = 0.005
DEFAULT_ROTATION_STEP_RAD = math.radians(1.0)

# Per-command caps. A jog command asking for more than this is rejected before IK,
# so a fat-fingered step size cannot request a metre-scale Cartesian jump.
MAX_TRANSLATION_STEP_M = 0.05
MAX_ROTATION_STEP_RAD = math.radians(10.0)

# Move-to convergence. A jog step is one differential solve cycle, but an absolute
# Move-to (and its IK-existence probe) must drive the differential solver to the target,
# so it iterates solve cycles until the achieved TCP is within tolerance or the budget
# is spent — an exhausted budget means the pose is unreachable, not that a step skipped.
MOVE_TO_MAX_CYCLES = 80
MOVE_TO_TOLERANCE_M = 0.002
MOVE_TO_TOLERANCE_RAD = math.radians(1.0)

# The velocity scale is a dimensionless multiplier a singularity monitor (WP-2D-02)
# lowers to damp the jog near a degeneracy. It never exceeds unity and never reaches
# zero — a zero scale would make the jog silently inert, indistinguishable from a hold.
FULL_VELOCITY_SCALE = 1.0
MIN_VELOCITY_SCALE = 1e-3

# MJCF handles in the v2 cell asset. The lifter is the prismatic joint that raises
# both arm bases; its displacement is the `q_lift` the base frame must reflect.
LIFTER_JOINT = "openarm_lifter_joint"
BASE_LINK_BY_SIDE = {
    "right": "openarm_right_base_link",
    "left": "openarm_left_base_link",
}
# The gripper's inner-finger body. Its offset from the EE control point is what makes
# the grasp point a distinct TCP from the default flange reference (acceptance ⑥).
INNER_FINGER_BY_SIDE = {
    "right": "openarm_right_ee_inner_finger",
    "left": "openarm_left_ee_inner_finger",
}

SIDES = ("right", "left")

# Solution layout mirrors sim.ik: two arms of eight driver values (seven joints plus
# one gripper), right side first.
SIDE_WIDTH = 8
ARM_JOINTS_PER_SIDE = 7
BIMANUAL_WIDTH = 16

# The UI note acceptance ⑥ requires: the default TCP is the wrist/flange control
# point, not the point between the fingers. A teaching operator who assumes the jog
# frame sits at the grasp point will mis-place every taught pose by the flange-to-tip
# offset, so the distinction is surfaced, not left implicit.
TCP_DEFAULT_NOTE = (
    "Default TCP is the EE control point (wrist flange), NOT the grasp point between "
    "the fingers. Select the grasp TCP explicitly to jog about the fingertip."
)

# The note the first-line-of-defense cost carries (02b §4.3): a legal IK solution can
# still be clamped or held by the adapter, so 'IK succeeded but the arm did not move'
# is a normal, explainable outcome — surfaced here so a UI can explain it.
CLAMP_FIRST_DEFENSE_NOTE = (
    "The IK adapter is the first line of defense: a solution that leaves the canonical "
    "mechanical limits is discarded and the jog stops. A held step with a reachable "
    "target is expected behaviour, not a fault."
)
