"""Whole-point mirror over the WP-2D-05 TeachingPoint schema.

The mirror transforms exactly three fields — arm side, joint vector, EE pose — and
carries everything else verbatim, so the zero record the WP-2D-05 replay gate checks and
the shared lifter height travel with the mirrored point. The result is re-validated by
the same schema that made the source.
"""

from __future__ import annotations

import numpy as np

from backend.mirror import mirror_teaching_point
from backend.mirror.constants import GRIPPER_OPEN_RAD, POSITION_REFLECT, QUAT_REFLECT
from tests.wp2d08 import right_sample_point


def test_arm_side_flips() -> None:
    assert mirror_teaching_point(right_sample_point()).arm_side == "left"


def test_q_urdf_mirrors_by_the_convention() -> None:
    mirrored = mirror_teaching_point(right_sample_point()).q_urdf
    expected = np.array([-0.1, 0.2, -0.3, 1.2, 0.4, -0.5, 0.6, GRIPPER_OPEN_RAD])
    assert np.allclose(mirrored, expected)


def test_ee_pose_reflects_across_the_sagittal_plane() -> None:
    source = right_sample_point()
    mirrored = np.array(mirror_teaching_point(source).ee_pose, dtype=float)
    origin = np.array(source.ee_pose, dtype=float)
    assert np.allclose(mirrored[:3], origin[:3] * POSITION_REFLECT)
    assert np.allclose(mirrored[3:], origin[3:] * QUAT_REFLECT)


def test_zero_record_and_lifter_and_metadata_are_carried() -> None:
    source = right_sample_point()
    mirrored = mirror_teaching_point(source)
    assert mirrored.name == source.name
    assert mirrored.gain_profile == source.gain_profile
    assert mirrored.zero_method == source.zero_method
    assert mirrored.zeroed_at == source.zeroed_at
    assert mirrored.q_lift == source.q_lift
    assert mirrored.timestamp == source.timestamp


def test_point_mirror_is_an_involution() -> None:
    source = right_sample_point()
    assert mirror_teaching_point(mirror_teaching_point(source)) == source


def test_result_is_a_validated_left_point() -> None:
    # replace() reruns __post_init__, so the mirrored point is a schema-valid left point:
    # width-8 q_urdf, width-7 ee_pose, arm_side in the domain.
    mirrored = mirror_teaching_point(right_sample_point())
    assert mirrored.arm_side == "left"
    assert len(mirrored.q_urdf) == 8
    assert len(mirrored.ee_pose) == 7
