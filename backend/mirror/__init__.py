"""Mirror teaching for the bimanual OpenArm (WP-2D-08, FR-MAN-046 / FR-MAN-017).

One arm's teaching point becomes the opposite arm's symmetric point: the seven arm
joints reflect by ``[-1,-1,-1,+1,-1,-1,-1]`` (joint4 alone same-sign), the gripper
opening flips sign, and the EE pose reflects across the cell's sagittal plane. The
transform is an exact involution (numeric verification error 0.0) and its sign vector is
cross-checked against the pinned per-side joint limits, which is where flipping joint4 is
caught. The gripper mirror is derived from the convention, not from LeRobot's left-gripper
limit, which ships the FR-MAN-017 mirror bug.
"""

from __future__ import annotations

from backend.mirror.convention import (
    mirror_arm_joints,
    mirror_arm_side,
    mirror_gripper,
    mirror_q_urdf,
    reflect_ee_pose,
)
from backend.mirror.teaching import mirror_teaching_point
from backend.mirror.verify import (
    convention_matches_pinned_limits,
    gripper_mirror_opposes_lerobot_bug,
    involution_error,
)

__all__ = [
    "convention_matches_pinned_limits",
    "gripper_mirror_opposes_lerobot_bug",
    "involution_error",
    "mirror_arm_joints",
    "mirror_arm_side",
    "mirror_gripper",
    "mirror_q_urdf",
    "mirror_teaching_point",
    "reflect_ee_pose",
]
