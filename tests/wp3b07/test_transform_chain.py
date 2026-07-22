"""Acceptance ④ (CG-3B-07d) — the coordinate transform chain, deterministic and once.

`FR-TEL-025`: XR controller pose -> robot-world EE target via `R_ROBOT` + offset,
applied at exactly one place (`frame_applied`). The chain is deterministic: a fixed
synthetic input yields a fixed pose. `Q_ROBOT` is proven to be the same rotation as
`R_ROBOT`, the axis checksum from `05` §2.8 is verified, and applying the transform
twice is shown to diverge from applying it once (the double-transform hazard).
"""

from __future__ import annotations

import pytest

from backend.teleop.vr_udp import R_ROBOT, parse_datagram, transform_controller_pose
from backend.teleop.vr_udp.constants import FRAME_OFFSET, Q_ROBOT
from backend.teleop.vr_udp.geometry import quat_to_mat3, rotate_vector, unity_lh_to_rh_position
from contracts.fixtures.vr_pose_stream import SyntheticVrPoseStream
from tests.wp3b07._support import datagram_from_sample

IDENTITY_QUAT_XYZW = (0.0, 0.0, 0.0, 1.0)


def test_sample_zero_transforms_to_known_world_pose() -> None:
    """The first synthetic sample maps to an exact, hand-computed world pose."""
    stream = SyntheticVrPoseStream()
    frame = parse_datagram(datagram_from_sample(stream, 0), receive_mono_ns=1)
    left = frame.arm("left").world_pose
    right = frame.arm("right").world_pose
    assert left == pytest.approx((0.1, -0.1, 1.2, 0.5, 0.5, -0.5, -0.5))
    assert right == pytest.approx((0.1, -0.5, 1.2, 0.5, 0.5, -0.5, -0.5))


def test_transform_is_deterministic_across_reparse() -> None:
    """Re-parsing the same stream reproduces every pose bit-for-bit."""
    stream = SyntheticVrPoseStream()
    first = [
        parse_datagram(datagram_from_sample(stream, i), receive_mono_ns=i).arm("left").world_pose
        for i in range(16)
    ]
    second = [
        parse_datagram(datagram_from_sample(stream, i), receive_mono_ns=i + 1)
        .arm("left")
        .world_pose
        for i in range(16)
    ]
    assert first == second


def test_q_robot_reconstructs_r_robot() -> None:
    """`Q_ROBOT` and `R_ROBOT` are one rotation in two spellings; they must not drift."""
    rebuilt = quat_to_mat3(Q_ROBOT)
    for i in range(3):
        for j in range(3):
            assert rebuilt[i][j] == pytest.approx(R_ROBOT[i][j])


def test_axis_checksum_from_spec() -> None:
    """`05` §2.8 checksum: x_robot = -z_xr, y_robot = -x_xr, z_robot = +y_xr (pre-offset)."""
    xr = (0.3, 0.7, 0.9)  # a right-handed XR position (post Unity LH->RH)
    robot = rotate_vector(R_ROBOT, xr)
    assert robot == pytest.approx((-xr[2], -xr[0], xr[1]))


def test_unity_z_negation() -> None:
    """Unity LH->RH negates Z before the rotation."""
    assert unity_lh_to_rh_position((1.0, 2.0, 3.0)) == (1.0, 2.0, -3.0)


def test_offset_is_added_after_rotation() -> None:
    """A zero-position controller lands exactly on the frame offset."""
    pose = transform_controller_pose((0.0, 0.0, 0.0), IDENTITY_QUAT_XYZW)
    assert pose[:3] == pytest.approx(FRAME_OFFSET)


def test_double_transform_diverges_from_single() -> None:
    """Applying the chain to its own output flips the axes — the double-transform hazard.

    This is why the source declares `frame_applied` and a consumer must not re-apply
    it: feeding the world-frame pose back through the chain does not equal the pose.
    """
    once = transform_controller_pose((0.2, 0.4, 0.6), IDENTITY_QUAT_XYZW)
    twice = transform_controller_pose((once[0], once[1], once[2]), IDENTITY_QUAT_XYZW)
    assert twice[:3] != pytest.approx(once[:3])


def test_reference_subtraction_shifts_position() -> None:
    """A NECK reference subtracts before rotation, shifting the world position."""
    without = transform_controller_pose((0.5, 0.0, 0.0), IDENTITY_QUAT_XYZW)
    with_ref = transform_controller_pose(
        (0.5, 0.0, 0.0), IDENTITY_QUAT_XYZW, reference=(0.2, 0.0, 0.0)
    )
    assert with_ref[:3] != pytest.approx(without[:3])


def test_frame_applied_flag_is_declared() -> None:
    """Every parsed frame declares the world transform already ran (no re-apply)."""
    stream = SyntheticVrPoseStream()
    frame = parse_datagram(datagram_from_sample(stream, 0), receive_mono_ns=1)
    assert frame.frame_applied is True
