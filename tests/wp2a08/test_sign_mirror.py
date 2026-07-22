"""Acceptance (2) — a config violating `left = [-hi_right, -lo_right]` is load-refused.

This is the FAIL_BLOCKING invariant: the LeRobot bug is a left gripper configured with
the right's un-mirrored limits (`-65..0` instead of `0..+65`), which silently clips the
left open command to zero so the left gripper never opens. The record refuses that
config at construction and at load, both from an in-memory build and from disk bytes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.gripper_endpoint.errors import GripperConfigError
from backend.gripper_endpoint.persistence import (
    gripper_record_path_for,
    load_gripper_record,
    save_gripper_record,
)
from backend.gripper_endpoint.schema import GripperLimits, GripperMirrorRecord, mirror_limits
from tests.wp2a08.conftest import (
    LEFT_HI_RAD,
    LEFT_LO_RAD,
    RIGHT_HI_RAD,
    RIGHT_LO_RAD,
    make_record,
)


def test_mirror_correct_config_loads(valid_record: GripperMirrorRecord) -> None:
    """The mirror-correct left limits `[0, +65deg]` build and validate without error."""
    assert valid_record.left_limits.lo_rad == pytest.approx(LEFT_LO_RAD)
    assert valid_record.left_limits.hi_rad == pytest.approx(LEFT_HI_RAD)


def test_mirror_formula_matches_fr_tel_059() -> None:
    """The mirror of right `[-65deg, 0]` is exactly left `[0, +65deg]` (FR-TEL-059)."""
    want_lo, want_hi = mirror_limits(GripperLimits("right", RIGHT_LO_RAD, RIGHT_HI_RAD))
    assert (want_lo, want_hi) == pytest.approx((LEFT_LO_RAD, LEFT_HI_RAD))


def test_unmirrored_left_is_refused_in_memory() -> None:
    """Left limits equal to the right's (the LeRobot bug) are refused at construction."""
    with pytest.raises(GripperConfigError, match="sign-mirror"):
        make_record(left_lo=RIGHT_LO_RAD, left_hi=RIGHT_HI_RAD)


def test_unmirrored_left_is_refused_from_disk(
    tmp_path: Path, valid_record: GripperMirrorRecord
) -> None:
    """A persisted-then-corrupted mirror relation is refused at load, not silently kept."""
    path = gripper_record_path_for(tmp_path, "armpair")
    save_gripper_record(path, valid_record)

    payload = json.loads(path.read_text(encoding="utf-8"))
    # Break only the left limits, then re-checksum so the refusal is the mirror rule,
    # not the checksum guard doing the work.
    payload["left_limits"]["lo_rad"] = RIGHT_LO_RAD
    payload["left_limits"]["hi_rad"] = RIGHT_HI_RAD
    payload.pop("checksum", None)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(GripperConfigError, match="sign-mirror"):
        load_gripper_record(path)


def test_near_miss_mirror_is_refused() -> None:
    """A left limit off by more than tolerance is refused (the relation is exact)."""
    with pytest.raises(GripperConfigError, match="sign-mirror"):
        make_record(left_lo=LEFT_LO_RAD + 0.01, left_hi=LEFT_HI_RAD)
