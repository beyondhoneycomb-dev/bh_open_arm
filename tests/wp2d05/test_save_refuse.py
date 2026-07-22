"""CG-2D-05a (acceptance ①) — a point lacking zero_method/zeroed_at is save-refused.

A teaching point without the zero reference it was taught against is un-replayable, so
the schema refuses to represent one — at construction, at JSON load, and at file load.
There is no path that persists a zero-less point to be discovered later.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.calibration import ZeroMethod
from backend.teaching import (
    TeachingPoint,
    TeachingPointError,
    load_teaching_points,
)

from . import RIGHT, ZEROED_AT_A, make_point


def _valid_dict() -> dict:
    return make_point("p1").to_json_dict()


def test_empty_zeroed_at_is_refused_at_construction() -> None:
    with pytest.raises(TeachingPointError, match="zeroed_at"):
        TeachingPoint(
            name="p1",
            arm_side=RIGHT,
            q_urdf=[0.0] * 8,
            ee_pose=[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
            gain_profile="default",
            zero_method=ZeroMethod.LEROBOT_HANGING,
            zeroed_at="",
            q_lift=0.0,
            timestamp="2026-07-22T00:00:00+00:00",
        )


def test_missing_zeroed_at_key_is_refused_on_json_load() -> None:
    data = _valid_dict()
    del data["zeroed_at"]
    with pytest.raises(TeachingPointError, match="missing required field"):
        TeachingPoint.from_json_dict(data)


def test_missing_zero_method_key_is_refused_on_json_load() -> None:
    data = _valid_dict()
    del data["zero_method"]
    with pytest.raises(TeachingPointError, match="missing required field"):
        TeachingPoint.from_json_dict(data)


def test_unknown_zero_method_value_is_refused() -> None:
    data = _valid_dict()
    data["zero_method"] = "eyeballed_it"
    with pytest.raises(TeachingPointError, match="zero_method is not a known"):
        TeachingPoint.from_json_dict(data)


def test_collection_with_a_zeroless_point_is_refused_at_file_load(tmp_path: Path) -> None:
    # A hand-edited file that dropped one point's zeroed_at must be rejected at read
    # time, not loaded with a silent hole the replay gate then cannot interpret.
    good = make_point("p1").to_json_dict()
    zeroless = make_point("p2").to_json_dict()
    del zeroless["zeroed_at"]
    body = {"version": 1, "side": RIGHT, "points": [good, zeroless]}
    path = tmp_path / "oa_right.oa_teach.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(TeachingPointError):
        load_teaching_points(path)


def test_a_valid_point_carries_both_zero_fields() -> None:
    point = make_point("p1")
    assert point.zero_method is ZeroMethod.LEROBOT_HANGING
    assert point.zeroed_at == ZEROED_AT_A
