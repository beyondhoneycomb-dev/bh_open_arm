"""CG-2D-05c (acceptance ③) — left and right never share one collection instance.

The two arms carry asymmetric limits and zero offsets (mirror geometry), so a store is
per-arm and refuses a foreign-arm point, and a right point never gates as replayable
against a left zero record. Two side-tagged stores, never one shared list.
"""

from __future__ import annotations

import pytest

from backend.teaching import (
    ReplayDecision,
    TeachingPointStore,
    TeachingStoreError,
    ZeroIdentity,
    evaluate_replay,
)

from . import LEFT, RIGHT, identity, make_calibration, make_point


def test_two_stores_are_distinct_instances_with_separate_lists() -> None:
    left = TeachingPointStore(LEFT)
    right = TeachingPointStore(RIGHT)
    assert left is not right
    left.add(make_point("l1", side=LEFT, zero=identity(LEFT)))
    assert right.names() == ()
    assert left.names() == ("l1",)


def test_right_store_refuses_a_left_point() -> None:
    right = TeachingPointStore(RIGHT)
    left_point = make_point("l1", side=LEFT, zero=identity(LEFT))
    with pytest.raises(TeachingStoreError, match="right store"):
        right.add(left_point)


def test_left_store_refuses_a_right_point() -> None:
    left = TeachingPointStore(LEFT)
    right_point = make_point("r1", side=RIGHT, zero=identity(RIGHT))
    with pytest.raises(TeachingStoreError, match="left store"):
        left.add(right_point)


def test_left_and_right_zero_records_are_asymmetric() -> None:
    # The offsets differ between arms, so the two records are not interchangeable — the
    # asymmetry that makes a shared instance wrong in the first place.
    left_cal = make_calibration(LEFT)
    right_cal = make_calibration(RIGHT)
    assert left_cal.urdf_zero_offset != right_cal.urdf_zero_offset


def test_right_point_never_replayable_against_left_record() -> None:
    right_point = make_point("r1", side=RIGHT, zero=identity(RIGHT))
    left_identity = ZeroIdentity.from_calibration(make_calibration(LEFT))
    verdict = evaluate_replay(right_point, left_identity)
    assert verdict.decision is ReplayDecision.BLOCKED


def test_store_rejects_an_unknown_side() -> None:
    with pytest.raises(TeachingStoreError, match="side must be"):
        TeachingPointStore("middle")
