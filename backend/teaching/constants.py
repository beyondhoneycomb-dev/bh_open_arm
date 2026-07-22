"""Named quantities for the teaching-point store (WP-2D-05).

The vector widths are tied to their upstream sources rather than re-declared: a
teaching point's ``q_urdf`` is one value per motor in the frozen calibration order
(``MOTOR_COUNT``), so binding it here keeps the two from drifting into two truths
about how wide "one arm's joint vector" is. The pose width matches the float[7]
layout ``openarm_control`` and ``backend.cartesian_jog`` already use.
"""

from __future__ import annotations

from backend.calibration.schema import MOTOR_COUNT

# One value per motor in MOTOR_ORDER (seven joints plus the gripper). Bound to the
# calibration width so a schema change there cannot leave a teaching point claiming
# a different arm shape than the zero record it depends on.
Q_URDF_WIDTH = MOTOR_COUNT

# EE pose as float[7] = [px, py, pz, qw, qx, qy, qz]. This is the layout
# openarm_control returns and backend.cartesian_jog stores; a teaching point records
# the pose it was taught at in exactly that shape so a reader never has to guess the
# quaternion order. Declared here (not imported) so the core store carries no sim
# dependency — backend.cartesian_jog.frames imports mujoco at module load.
EE_POSE_WIDTH = 7

# The two follower arms. A teaching point belongs to exactly one; a store instance
# serves exactly one. Left and right carry asymmetric limits and zero offsets, so
# they are never one shared collection (acceptance ③).
ARM_SIDES = ("left", "right")

# On-disk collection generation and file suffix. A shape change is a new generation,
# never an in-place edit of this literal. The suffix is distinct from the calibration
# (`.oa_cal.json`) and gripper (`.oa_gripper.json`) records so the three persistence
# mechanisms never read each other's bytes.
COLLECTION_VERSION = 1
COLLECTION_SUFFIX = ".oa_teach.json"
