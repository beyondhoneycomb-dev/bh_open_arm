"""Domain constants for seed-profile isolation and the v1->v2 promotion diff.

The robot-version tag and the joint-vector field name are imported from WP-2B-01's converter
rather than re-declared, so the seed package and the converter can never disagree about what
"v1" means or which field carries the pose that takes joint2's +pi/2 shift.
"""

from __future__ import annotations

from backend.dynamics.constants import ANGLE_VECTOR_FIELDS, ROBOT_VERSION_V1

# The reserved name of the isolated profile. There is exactly one seed per arm generation.
SEED_PROFILE_NAME = "seed"

# A seed is v1 by definition (FR-SAF-031): the promotion target is v2, the seed is its origin.
SEED_ROBOT_VERSION = ROBOT_VERSION_V1

# The angle field the promotion measures per-joint relative error on. It is WP-2B-01's single
# angle-vector field — the pose that carries the joint2 +pi/2 zero shift, so it is exactly where
# a promotion's material change surfaces for the operator to see before approving.
SEED_POSE_FIELD = ANGLE_VECTOR_FIELDS[0]

# Below this |v1| magnitude (radians) the per-joint relative error is a division by ~0 and is
# reported as undefined rather than a spurious infinity; the absolute error is still shown.
RELATIVE_ERROR_EPSILON_RAD = 1e-9

# The digest algorithm binding an approval to the exact report it acknowledged. Truncated to a
# readable prefix for display and comparison — collision resistance is not the property needed;
# tamper-evidence between "the report shown" and "the report approved" is.
DIGEST_ALGORITHM = "sha256"
DIGEST_DISPLAY_LEN = 16
