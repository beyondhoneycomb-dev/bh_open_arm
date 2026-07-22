"""Named quantities for the left/right mirror-teaching transform (WP-2D-08).

The mirror convention is `04` §2.3 / FR-MAN-046: the seven arm joints reflect by a
fixed sign vector with joint4 alone kept same-sign, and the gripper opening flips sign.
Every literal a reviewer must trust to read the convention lives here, not spelled out
at a call site, so the one place to check the convention against the spec is this file.
"""

from __future__ import annotations

import numpy as np

# `04` §2.3 / FR-MAN-046: q_left = [-1,-1,-1,+1,-1,-1,-1] ⊙ q_right. joint4 (index 3)
# is the sole same-sign joint; flipping its sign yields a wrong symmetric point
# (FR-MAN-046 negative branch = FAIL_BLOCKING). Read-only so the shared constant cannot
# be mutated out from under a caller.
ARM_MIRROR_SIGNS = np.array([-1.0, -1.0, -1.0, 1.0, -1.0, -1.0, -1.0])
ARM_MIRROR_SIGNS.setflags(write=False)
JOINT4_INDEX = 3

# q_urdf layout (FR-MAN-039): seven arm joints then one gripper driver value, the same
# per-side driver vector sim.ik / cartesian_jog produce.
ARM_JOINT_COUNT = 7
GRIPPER_INDEX = 7
Q_URDF_WIDTH = 8

# ee_pose layout (FR-MAN-039): [px, py, pz, qw, qx, qy, qz] in the world frame.
POSE_WIDTH = 7

# The two arm bases sit symmetric across the cell's sagittal (XZ) plane (base y = ∓0.031
# m, `04` §2.3), so the world-frame mirror of a pose reflects the y axis: position by
# (px, -py, pz) and a rotation by the sign pattern (qw, -qx, qy, -qz). Both patterns are
# verified equal to the FK of the joint-space mirror to floating point in the acceptance
# suite (test_fk_equality), so the pose reflection stays consistent with the joint mirror.
POSITION_REFLECT = np.array([1.0, -1.0, 1.0])
POSITION_REFLECT.setflags(write=False)
QUAT_REFLECT = np.array([1.0, -1.0, 1.0, -1.0])
QUAT_REFLECT.setflags(write=False)

# Gripper URDF finger-joint open ranges (FR-MAN-046): the right gripper opens negative,
# the left opens positive. The mirror is the sign flip g_left = -g_right, which carries
# the right range [-GRIPPER_OPEN_RAD, 0] onto the left range [0, +GRIPPER_OPEN_RAD] — the
# FR-MAN-017 relation left = [-hi_right, -lo_right]. This is derived from the convention
# alone and is independent of LeRobot's left-gripper soft limit, which ships the mirror
# bug (both sides negative, `04` §3.5 / FR-MAN-017); that buggy limit is never the oracle.
GRIPPER_OPEN_RAD = 0.7854

SIDES = ("right", "left")
OPPOSITE_SIDE = {"right": "left", "left": "right"}
