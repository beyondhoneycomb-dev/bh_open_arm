"""Atomic file IO for the teaching-point collection (02b §4 산출, atomic reuse)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.teaching import (
    TeachingCollectionError,
    TeachingPointStore,
    load_teaching_points,
    save_teaching_points_atomic,
    teaching_points_path_for,
)

from . import RIGHT, ZEROED_AT_B, identity, make_point


def _saved_store(tmp_path: Path) -> tuple[Path, TeachingPointStore]:
    store = TeachingPointStore(RIGHT)
    store.add(make_point("a", q_urdf=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]))
    store.add(make_point("b", zero=identity(RIGHT, zeroed_at=ZEROED_AT_B)))
    path = teaching_points_path_for(tmp_path, "oa_right")
    save_teaching_points_atomic(path, store)
    return path, store


def test_round_trip_preserves_side_order_and_fields(tmp_path: Path) -> None:
    path, store = _saved_store(tmp_path)
    loaded = load_teaching_points(path)
    assert loaded.side == store.side
    assert loaded.names() == store.names()
    for original, restored in zip(store.points(), loaded.points(), strict=True):
        assert restored.to_json_dict() == original.to_json_dict()


def test_saved_file_is_the_expected_path_and_valid_json(tmp_path: Path) -> None:
    path, _ = _saved_store(tmp_path)
    assert path.name == "oa_right.oa_teach.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["version"] == 1
    assert body["side"] == RIGHT
    assert [p["name"] for p in body["points"]] == ["a", "b"]


def test_save_leaves_no_temp_files_behind(tmp_path: Path) -> None:
    path, _ = _saved_store(tmp_path)
    siblings = list(path.parent.iterdir())
    assert siblings == [path]


def test_overwrite_replaces_the_collection_atomically(tmp_path: Path) -> None:
    path, _ = _saved_store(tmp_path)
    smaller = TeachingPointStore(RIGHT)
    smaller.add(make_point("only"))
    save_teaching_points_atomic(path, smaller)
    assert load_teaching_points(path).names() == ("only",)
    assert list(path.parent.iterdir()) == [path]


def test_load_refuses_a_wrong_version(tmp_path: Path) -> None:
    path = tmp_path / "oa_right.oa_teach.json"
    body = {"version": 99, "side": RIGHT, "points": []}
    path.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(TeachingCollectionError, match="version"):
        load_teaching_points(path)


def test_load_refuses_a_missing_side(tmp_path: Path) -> None:
    path = tmp_path / "oa_right.oa_teach.json"
    body = {"version": 1, "points": []}
    path.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(TeachingCollectionError, match="side"):
        load_teaching_points(path)


def test_load_refuses_a_cross_arm_point_in_the_collection(tmp_path: Path) -> None:
    # A right collection carrying a left point is a corrupt file; the store invariant is
    # enforced on load exactly as it is on add.
    right = make_point("r", side=RIGHT).to_json_dict()
    left = make_point("l", side="left", zero=identity("left")).to_json_dict()
    path = tmp_path / "oa_right.oa_teach.json"
    path.write_text(json.dumps({"version": 1, "side": RIGHT, "points": [right, left]}), "utf-8")
    with pytest.raises(Exception, match="right store|cannot hold"):
        load_teaching_points(path)
