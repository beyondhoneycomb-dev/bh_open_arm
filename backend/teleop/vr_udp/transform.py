"""The coordinate-transform chain: XR controller pose to robot-world EE target.

One function, applied at exactly one place in the pipeline (`05` §2.8, no double
transform). The chain is: Unity left-handed to right-handed axis conversion, an
optional NECK reference-pose subtraction, the `R_ROBOT` rotation, and the
`FRAME_OFFSET` translation. Orientation is rotated by `Q_ROBOT`, the quaternion
twin of `R_ROBOT`. The output is `float32[7] = [px, py, pz, qw, qx, qy, qz]`,
scalar-first (`FR-TEL-025`), already in the MuJoCo world frame.

The operator-alignment rotation (`Rz(90°)`, "controller held aligned -> EE home")
is deliberately NOT applied here — that is trigger-alignment, owned by WP-3B-09.
This layer is the raw frame change only.
"""

from __future__ import annotations

from backend.teleop.vr_udp.constants import FRAME_OFFSET, POSE_DIMENSION, Q_ROBOT, R_ROBOT
from backend.teleop.vr_udp.geometry import (
    Vec3,
    add,
    quat_multiply,
    rotate_vector,
    subtract,
    unity_lh_to_rh_position,
    unity_lh_to_rh_quaternion,
)

# `float32[7] = [px, py, pz, qw, qx, qy, qz]`, scalar-first world-frame EE target.
WorldPose = tuple[float, float, float, float, float, float, float]


def transform_controller_pose(
    position: Vec3,
    quaternion_xyzw: tuple[float, float, float, float],
    reference: Vec3 | None = None,
) -> WorldPose:
    """Map one XR controller pose into a robot-world EE target pose.

    Args:
        position: Unity controller position `(x, y, z)` (wire `lc`/`rc`).
        quaternion_xyzw: Unity controller orientation, scalar-last `(x, y, z, w)`
            (wire `lt`/`rt`).
        reference: Optional NECK reference position (wire `rf`) subtracted before
            rotation. None on the synthetic stream, where the subtraction is
            identity; its real-headset semantics are unconfirmed (`05` §5 U-12).

    Returns:
        (WorldPose) `[px, py, pz, qw, qx, qy, qz]`, scalar-first, robot-world frame.
    """
    position_rh = unity_lh_to_rh_position(position)
    if reference is not None:
        position_rh = subtract(position_rh, unity_lh_to_rh_position(reference))
    position_world = add(rotate_vector(R_ROBOT, position_rh), FRAME_OFFSET)

    orientation_rh = unity_lh_to_rh_quaternion(quaternion_xyzw)
    orientation_world = quat_multiply(Q_ROBOT, orientation_rh)

    pose = (*position_world, *orientation_world)
    assert len(pose) == POSE_DIMENSION  # the contract's float32[7] shape
    return pose
