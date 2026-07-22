"""CG-2B-10b (first half) — the promotion report shows per-joint relative error.

The report is the operator's view of what the v1->v2 conversion changes. joint2's +pi/2 shift is
the material change and must show up there as a large relative error and ~zero elsewhere — the
fingerprint that the shift landed and is confined to the shoulder. The report activates nothing.
"""

from __future__ import annotations

import math

import pytest

from backend.dynamics.constants import ARM_JOINT_COUNT, J2_ZERO_SHIFT_RAD, JOINT2_INDEX
from backend.dynamics.converter import JointFrameConverter
from backend.dynamics.provenance import Provenance
from backend.seed_profile.profile import SeedProfile
from backend.seed_profile.promotion import build_promotion_report


def test_report_has_one_row_per_joint(
    seed: SeedProfile, converter: JointFrameConverter, target_provenance: Provenance
) -> None:
    """Per-joint relative error is reported for every arm joint."""
    report = build_promotion_report(seed, converter, target_provenance)
    assert len(report.per_joint) == ARM_JOINT_COUNT
    assert [row.joint_index for row in report.per_joint] == list(range(ARM_JOINT_COUNT))


def test_joint2_is_the_shift_fingerprint(
    seed: SeedProfile, converter: JointFrameConverter, target_provenance: Provenance
) -> None:
    """joint2 carries an absolute error of exactly +pi/2; the default converter moves no other."""
    report = build_promotion_report(seed, converter, target_provenance)
    for row in report.per_joint:
        if row.joint_index == JOINT2_INDEX:
            assert row.absolute_error == pytest.approx(J2_ZERO_SHIFT_RAD)
        else:
            assert row.absolute_error == pytest.approx(0.0)


def test_joint2_relative_error_is_largest_and_defined(
    seed: SeedProfile, converter: JointFrameConverter, target_provenance: Provenance
) -> None:
    """joint2's relative error is defined and the largest — the change the operator must weigh."""
    report = build_promotion_report(seed, converter, target_provenance)
    joint2 = report.per_joint[JOINT2_INDEX]
    assert joint2.relative_error is not None
    assert joint2.relative_error == pytest.approx(J2_ZERO_SHIFT_RAD / abs(joint2.v1_value))
    others = [
        row.relative_error
        for row in report.per_joint
        if row.joint_index != JOINT2_INDEX and row.relative_error is not None
    ]
    assert all(joint2.relative_error > value for value in others)


def test_relative_error_undefined_when_v1_near_zero(
    converter: JointFrameConverter, target_provenance: Provenance
) -> None:
    """A joint whose v1 value is ~0 reports relative error as undefined, not a spurious infinity."""
    raw = {
        "provenance": {
            "source_repo": "openarm_teleop",
            "commit_sha": "0" * 39 + "1",
            "path": "config/follower.yaml",
            "robot_version": "1.0",
            "identified_on": "2025-07-23",
        },
        "seed_pose_rad": [0.0, 0.30, 0.0, -1.20, 0.0, 0.90, 0.0],
    }
    report = build_promotion_report(SeedProfile.from_mapping(raw), converter, target_provenance)
    zero_joint = report.per_joint[0]
    assert zero_joint.v1_value == pytest.approx(0.0)
    assert zero_joint.relative_error is None


def test_report_does_not_activate(
    seed: SeedProfile, converter: JointFrameConverter, target_provenance: Provenance
) -> None:
    """Building a report activates nothing — activation is a separate, approval-gated step."""
    report = build_promotion_report(seed, converter, target_provenance)
    assert report.activated is False


def test_converted_asset_carries_the_v2_stamp(
    seed: SeedProfile, converter: JointFrameConverter, target_provenance: Provenance
) -> None:
    """The report's converted asset is v2-stamped — a first-class v2 asset, not a v1 in disguise."""
    report = build_promotion_report(seed, converter, target_provenance)
    assert report.converted_asset["provenance"]["robot_version"] == "2.0"


def test_format_table_shows_every_joint_and_the_shift(
    seed: SeedProfile, converter: JointFrameConverter, target_provenance: Provenance
) -> None:
    """The rendered table has a row per joint and a percentage for the shifted shoulder."""
    report = build_promotion_report(seed, converter, target_provenance)
    table = report.format_table()
    body_lines = table.splitlines()[2:]
    assert len(body_lines) == ARM_JOINT_COUNT
    assert "%" in body_lines[JOINT2_INDEX]


def test_digest_changes_with_the_conversion(
    seed: SeedProfile, converter: JointFrameConverter
) -> None:
    """A different v2 origin yields a different report digest, so an old approval stops matching."""
    from tests.wp2b10.conftest import make_v2_provenance

    report_a = build_promotion_report(seed, converter, make_v2_provenance())
    report_b = build_promotion_report(
        seed, converter, make_v2_provenance(identified_on="2026-08-01")
    )
    assert report_a.digest != report_b.digest


def test_unconvertible_seed_is_refused(
    converter: JointFrameConverter, target_provenance: Provenance
) -> None:
    """A seed carrying an unconvertible item is refused by the promotion (WP-2B-01 FR-SAF-033)."""
    from backend.dynamics.errors import DynamicsConversionError

    raw = {
        "provenance": {
            "source_repo": "openarm_teleop",
            "commit_sha": "0" * 39 + "1",
            "path": "config/follower.yaml",
            "robot_version": "1.0",
            "identified_on": "2025-07-23",
        },
        "seed_pose_rad": [0.0] * ARM_JOINT_COUNT,
        "inertials": {"link7": {"mass": 0.5}},
    }
    with pytest.raises(DynamicsConversionError, match="link7"):
        build_promotion_report(SeedProfile.from_mapping(raw), converter, target_provenance)


def test_shift_materially_moves_the_shoulder(
    seed: SeedProfile, converter: JointFrameConverter, target_provenance: Provenance
) -> None:
    """The shoulder's v2 value differs from its v1 value by a full quarter turn."""
    report = build_promotion_report(seed, converter, target_provenance)
    joint2 = report.per_joint[JOINT2_INDEX]
    assert not math.isclose(joint2.v1_value, joint2.v2_value)
    assert joint2.v2_value == pytest.approx(joint2.v1_value + J2_ZERO_SHIFT_RAD)
