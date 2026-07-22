"""Acceptance ② — the left gripper mirror is applied, not omitted (FR-MAN-046/017).

The trap the plan names: ``default_bimanual.yaml``'s ``reflect.include.joints`` lists
only ``[1,2,3,5,6,7]``, omitting both joint4 and the gripper, and LeRobot's left-gripper
soft limit ships the mirror bug (both bounds non-positive). Blindly following either
leaves the left gripper unmirrored — it never opens. The mirror must flip the gripper
sign so the left gripper opens ``+`` where the right opens ``-``.
"""

from __future__ import annotations

import pytest

from backend.mirror import mirror_gripper, mirror_q_urdf, mirror_teaching_point
from backend.mirror.constants import GRIPPER_INDEX, GRIPPER_OPEN_RAD
from tests.wp2d08 import right_sample_point


def test_right_open_gripper_mirrors_to_left_open() -> None:
    # Right opens negative (-0.7854); the mirrored left must open positive (+0.7854).
    assert mirror_gripper(-GRIPPER_OPEN_RAD) == pytest.approx(GRIPPER_OPEN_RAD)
    assert mirror_gripper(0.0) == 0.0


def test_q_urdf_gripper_element_flips_sign() -> None:
    q = [0.1, -0.2, 0.3, 1.2, -0.4, 0.5, -0.6, -GRIPPER_OPEN_RAD]
    mirrored = mirror_q_urdf(q)
    assert mirrored[GRIPPER_INDEX] == pytest.approx(GRIPPER_OPEN_RAD)
    assert mirrored[GRIPPER_INDEX] > 0.0


def test_point_mirror_applies_the_left_gripper() -> None:
    # The sample right point holds the gripper at its right open bound (-0.7854).
    left_point = mirror_teaching_point(right_sample_point())
    assert left_point.arm_side == "left"
    # The gripper is NOT carried over unchanged (that is the omission bug); it is flipped.
    assert left_point.q_urdf[GRIPPER_INDEX] == pytest.approx(GRIPPER_OPEN_RAD)


def test_mirror_opposes_lerobot_gripper_bug() -> None:
    pytest.importorskip("lerobot")
    from backend.mirror import gripper_mirror_opposes_lerobot_bug

    divergence = gripper_mirror_opposes_lerobot_bug()
    # LeRobot's left-gripper upper bound is non-positive (the bug); our mirror is positive.
    assert divergence.lerobot_left_upper_rad <= 0.0
    assert divergence.mirrored_open_rad > 0.0
    assert divergence.opposes_bug
