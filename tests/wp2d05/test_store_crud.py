"""CRUD, reorder, and duplicate over the per-arm teaching-point store (02b §4 산출)."""

from __future__ import annotations

import pytest

from backend.teaching import TeachingPointStore, TeachingStoreError

from . import RIGHT, ZEROED_AT_A, make_point


def _store_with(names: list[str]) -> TeachingPointStore:
    store = TeachingPointStore(RIGHT)
    for name in names:
        store.add(make_point(name))
    return store


def test_add_get_and_order_are_preserved() -> None:
    store = _store_with(["a", "b", "c"])
    assert store.names() == ("a", "b", "c")
    assert store.get("b").name == "b"


def test_add_refuses_a_duplicate_name() -> None:
    store = _store_with(["a"])
    with pytest.raises(TeachingStoreError, match="already exists"):
        store.add(make_point("a"))


def test_get_and_remove_absent_name_raise() -> None:
    store = _store_with(["a"])
    with pytest.raises(TeachingStoreError, match="no teaching point named"):
        store.get("z")
    with pytest.raises(TeachingStoreError, match="no teaching point named"):
        store.remove("z")


def test_remove_deletes_only_the_named_point() -> None:
    store = _store_with(["a", "b", "c"])
    store.remove("b")
    assert store.names() == ("a", "c")


def test_update_replaces_in_place_keeping_position() -> None:
    store = _store_with(["a", "b", "c"])
    replacement = make_point("b", q_urdf=[9.0] * 8)
    store.update("b", replacement)
    assert store.names() == ("a", "b", "c")
    assert store.get("b").q_urdf == [9.0] * 8


def test_update_can_rename_but_not_onto_an_existing_name() -> None:
    store = _store_with(["a", "b"])
    store.update("a", make_point("a2"))
    assert store.names() == ("a2", "b")
    with pytest.raises(TeachingStoreError, match="already exists"):
        store.update("a2", make_point("b"))


def test_reorder_requires_a_permutation_of_current_names() -> None:
    store = _store_with(["a", "b", "c"])
    store.reorder(("c", "a", "b"))
    assert store.names() == ("c", "a", "b")
    with pytest.raises(TeachingStoreError, match="reorder requires"):
        store.reorder(("a", "b"))
    with pytest.raises(TeachingStoreError, match="reorder requires"):
        store.reorder(("a", "b", "z"))


def test_duplicate_copies_posture_and_zero_provenance_under_a_new_name() -> None:
    store = TeachingPointStore(RIGHT)
    store.add(make_point("orig", q_urdf=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]))
    copy = store.duplicate("orig", "orig_copy")
    assert store.names() == ("orig", "orig_copy")
    original = store.get("orig")
    assert copy.q_urdf == original.q_urdf
    assert copy.ee_pose == original.ee_pose
    # The copy is the same physical pose under a second label, so it keeps the zero
    # provenance and remains gated by the same identity.
    assert copy.zero_method is original.zero_method
    assert copy.zeroed_at == ZEROED_AT_A


def test_duplicate_refuses_an_existing_target_name() -> None:
    store = _store_with(["a", "b"])
    with pytest.raises(TeachingStoreError, match="already exists"):
        store.duplicate("a", "b")


def test_points_are_immutable_snapshots() -> None:
    store = _store_with(["a"])
    point = store.get("a")
    with pytest.raises((AttributeError, TypeError)):
        point.name = "mutated"  # type: ignore[misc]
