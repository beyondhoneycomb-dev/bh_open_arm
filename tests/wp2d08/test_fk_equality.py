"""Mirror numeric equality — the pose reflection equals the FK of the mirrored joints.

The reflection formula in ``reflect_ee_pose`` (position ``y -> -y``, quaternion
``(qw,-qx,qy,-qz)``) is only correct if it reproduces the real kinematics: mirror the
right arm's joints into the left arm, run FK on the committed cell asset (reused WP-2D-01
``KinematicFrames``), and the left EE pose must equal the geometric reflection of the
right EE pose. Proven across random joint states, lifter heights, and gripper openings,
so the pure-numpy reflection is not trusted on its own.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from backend.cartesian_jog.frames import KinematicFrames, pose_position, pose_quat
from backend.mirror.constants import Q_URDF_WIDTH
from backend.mirror.convention import mirror_q_urdf, reflect_ee_pose

# The bimanual driver solution packs one eight-value arm vector per side, right first, so
# a per-side slice is exactly the q_urdf width.
_SIDE = Q_URDF_WIDTH


def _quat_close(a: np.ndarray, b: np.ndarray) -> bool:
    # Unit quaternions double-cover SO(3): q and -q are the same rotation.
    return bool(min(np.abs(a - b).max(), np.abs(a + b).max()) < 1e-9)


def test_reflected_pose_equals_fk_of_mirrored_joints() -> None:
    frames = KinematicFrames()
    home16 = frames.home_solution()
    rng = np.random.default_rng(46)
    for _ in range(64):
        q_lift = float(rng.uniform(0.0, 0.3))
        right8 = home16[:_SIDE].copy()
        right8[:7] += rng.uniform(-0.4, 0.4, size=7)
        right8[3] = float(rng.uniform(0.0, 2.35))
        right8[7] = float(rng.uniform(-0.7854, 0.0))
        left8 = mirror_q_urdf(right8)

        sol_right = np.concatenate([right8, home16[_SIDE:]])
        sol_left = np.concatenate([home16[:_SIDE], left8])
        pose_right = frames.control_point_pose("right", sol_right, q_lift)
        pose_left = frames.control_point_pose("left", sol_left, q_lift)

        reflected = reflect_ee_pose(pose_right)
        assert np.allclose(pose_position(pose_left), reflected[:3], atol=1e-9)
        assert _quat_close(pose_quat(pose_left), reflected[3:])
