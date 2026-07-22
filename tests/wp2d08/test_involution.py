"""Acceptance ① — numeric verification error 0.0 (FR-MAN-046).

The mirror is its own inverse: mirroring a mirrored vector, pose, or whole point must
return the original bit-for-bit, because every element is one IEEE-754 sign flip. A
non-zero deviation would mean the convention is not a clean reflection.
"""

from __future__ import annotations

import numpy as np

from backend.mirror import involution_error, mirror_q_urdf, mirror_teaching_point
from backend.mirror.convention import mirror_arm_side, reflect_ee_pose
from tests.wp2d08 import right_sample_point

_RNG = np.random.default_rng(2008)


def _random_q_urdf() -> np.ndarray:
    joints = _RNG.uniform(-2.0, 2.0, size=7)
    gripper = _RNG.uniform(-0.7854, 0.0)
    return np.append(joints, gripper)


def test_q_urdf_involution_error_is_exactly_zero() -> None:
    for _ in range(500):
        assert involution_error(_random_q_urdf()) == 0.0


def test_double_mirror_restores_q_urdf_bitwise() -> None:
    q = _random_q_urdf()
    assert np.array_equal(mirror_q_urdf(mirror_q_urdf(q)), q)


def test_double_reflect_restores_ee_pose_bitwise() -> None:
    pose = _RNG.uniform(-1.0, 1.0, size=7)
    assert np.array_equal(reflect_ee_pose(reflect_ee_pose(pose)), pose)


def test_arm_side_is_an_involution() -> None:
    assert mirror_arm_side(mirror_arm_side("right")) == "right"
    assert mirror_arm_side(mirror_arm_side("left")) == "left"


def test_point_mirror_is_an_involution() -> None:
    point = right_sample_point()
    assert mirror_teaching_point(mirror_teaching_point(point)) == point
