"""Domain constants for the v1->v2 dynamics frame conversion and the provenance gate.

The joint-frame numbers are the v2 reference-arm convention read from the committed v2
MJCF (`sim/mjcf/v2/openarm_bimanual.xml`, the right arm — the arm whose joint2 range is
`[-0.17453, 3.3161]`) and from spec `12` §2.6. This module is the single place they live so
the converter and the gravity backend (WP-2B-02) never disagree about where joint2's zero
sits or which way a joint's positive rotation points.
"""

from __future__ import annotations

import math

# The exact joint2 zero-frame shift, v1 -> v2. Spec `12` §2.6 / FR-SAF-033 write it as
# +1.570796 rad; that is pi/2 rounded to six places, and the identity is exact — the v1
# range [-1.745329, 1.745329] plus pi/2 is the v2 range [-0.17453, 3.3161]. Feeding a v1
# gravity model at v2 angles without this shift swaps sin<->cos at the shoulder (joint2),
# the joint of largest gravity error, so a residual detector mis-fires forever (spec 12 §2.6).
J2_ZERO_SHIFT_RAD = math.pi / 2.0

# The seven arm joints of one follower arm. The gripper (J8) is not an arm joint and gets no
# frame conversion: its dynamics model does not exist in v2 (see UNCONVERTIBLE below).
ARM_JOINT_COUNT = 7

# joint2 is the only joint carrying a non-zero zero-frame offset. Zero-based index into a
# per-arm joint vector.
JOINT2_INDEX = 1

# The two robot-version tags this converter distinguishes. A v1 seed asset is tagged "1.0";
# only "2.0" is loadable into the v2 runtime under strict mode (FR-SAF-067).
ROBOT_VERSION_V1 = "1.0"
ROBOT_VERSION_V2 = "2.0"

# The mandatory provenance keys for every safety parameter (FR-SAF-067). A safety parameter
# missing any of these is unloadable: `follower.yaml` predates the v2.0 assets by ten months
# and was never edited after import, so human attention cannot be the thing that keeps a v1
# value out of the v2 runtime — provenance is.
PROVENANCE_FIELDS = ("source_repo", "commit_sha", "path", "robot_version", "identified_on")

# joint2 range endpoints, radians, used to verify the shift maps v1 exactly onto v2.
V1_JOINT2_RANGE_RAD = (-1.745329, 1.745329)
V2_JOINT2_RANGE_RAD = (-0.17453, 3.3161)

# The v2 reference-arm joint axes (unit vectors), read from the committed v2 MJCF right arm.
# These are the `joint_axes.yaml` reference FR-SAF-033 normalises a v1 model's axis signs
# onto; WP-2B-02 cross-checks its MuJoCo model against them.
V2_JOINT_AXES = (
    (0.0, -1.0, 0.0),  # joint1
    (-1.0, 0.0, 0.0),  # joint2
    (0.0, 0.0, -1.0),  # joint3
    (0.0, -1.0, 0.0),  # joint4
    (0.0, 0.0, -1.0),  # joint5
    (0.0, 1.0, 0.0),  # joint6
    (1.0, 0.0, 0.0),  # joint7
)

# The default identity axis-sign map: a v1 asset whose per-joint positive-rotation directions
# already agree with the v2 reference needs no sign flip. A v1 asset that disagrees builds a
# converter with its own map. joint2's sign is +1 — its correction is the zero offset, not a
# flip, which the monotonic v1->v2 range mapping confirms.
IDENTITY_AXIS_SIGNS = (1,) * ARM_JOINT_COUNT

# Items that have no v2 representation and so make a v1 asset unconvertible (spec 12 §2.6,
# FR-SAF-033). Keyed by the offending `inertials` link name; the value is the surfaced reason.
UNCONVERTIBLE_INERTIAL_LINKS = {
    "link7": (
        "v2 has no link7 body — the wrist-end mass moved into the end-effector, so a v1 "
        "link7 inertia has nowhere to live and cannot be carried across"
    ),
    "base_link": (
        "v2 re-expresses the base_link inertia in a rotated frame (v1 origin z=+0.0308 -> "
        "v2 origin y=-0.02582), so a v1 base_link inertia tensor cannot be converted directly"
    ),
}

# Top-level keys that carry a gripper/finger dynamics model. v2 defines no finger dynamics
# (inertials/nominal.yaml has no finger links, friction.yaml is empty) and a grip reaction is
# an ever-present torque offset, so a gripper model is unconvertible (spec 12 §2.6, FR-SAF-024).
GRIPPER_MODEL_KEYS = ("gripper_model", "finger_model")
GRIPPER_MODEL_REASON = (
    "v2 defines no gripper/finger dynamics model (no finger links in inertials, empty "
    "friction table), and grip reaction is a constant torque offset, so a v1 gripper model "
    "cannot be converted"
)

# Optional joint-vector fields the conversion transforms into the v2 frame when present.
# Angle fields carry the joint2 zero shift plus axis sign; rate/moment fields carry the axis
# sign only. Friction coefficients and gains are deliberately absent: they are frame-invariant
# magnitudes owned by the seed-isolation and identification packages (WP-2B-10 / WP-2B-07), not
# quantities this converter rewrites.
ANGLE_VECTOR_FIELDS = ("seed_pose_rad",)
TORQUE_VECTOR_FIELDS = ("seed_torque_nm",)
