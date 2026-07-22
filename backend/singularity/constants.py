"""Named quantities for the singularity monitor and elbow nullspace (WP-2D-02).

Thresholds live on the smallest singular value of the 6x7 arm Jacobian. That value
carries the Jacobian's own mixed units (metres and radians of EE motion per radian of
joint motion), so the defaults here are tuned against this model's observed range —
about 0.13 at the home pose, collapsing toward 0.002 as the elbow straightens — not a
physical constant. Both are settable at runtime (acceptance ③); the defaults are only
the power-on values.
"""

from __future__ import annotations

import math

# Driver/solution layout, mirrored from the reused sim.ik / cartesian_jog convention:
# two arms of eight driver values (seven joints + one gripper), right side first.
ARM_JOINTS_PER_SIDE = 7
SIDE_WIDTH = 8
BIMANUAL_WIDTH = 16

# A full Cartesian twist has six components (three linear, three angular); the arm
# Jacobian is therefore 6x7 and its singular values number six.
SPATIAL_DIM = 6

# Singularity thresholds on sigma_min. Above the warn value the jog runs at full speed;
# between warn and floor it is damped on a ramp; at or below the floor it holds, because
# no finite velocity scale carries a jog safely through an exact degeneracy.
DEFAULT_WARN_SIGMA_MIN = 0.05
DEFAULT_FLOOR_SIGMA_MIN = 0.01

# The velocity scale the damping ramp collapses to at the floor. Kept at or above the
# jog's own MIN_VELOCITY_SCALE so set_velocity_scale accepts it, and deliberately not
# zero: a zero scale is indistinguishable from a hold, and holding is the floor's job.
DAMPED_FLOOR_SCALE = 0.05

# The elbow swivel splits its requested angle into sub-steps no larger than this, each
# re-fixed to the frozen EE pose through the reused IK, so the EE stays fixed while the
# swivel spans a wide range. EE drift per committed sub-step grows roughly quadratically
# in the sub-step size, so a small sub-step buys a tight EE-fixed guarantee cheaply.
SWIVEL_SUBSTEP_MAX_RAD = 0.1

# What "the EE stays fixed" means for the swivel (acceptance ①), verified by forward
# kinematics. Matched to the jog's own Move-to reached-tolerance: the swivel holds the
# EE at the same pose by the same definition the jog uses to call a target "arrived".
EE_FIXED_TOLERANCE_M = 0.002
EE_FIXED_TOLERANCE_RAD = math.radians(1.0)

SIDES = ("right", "left")
