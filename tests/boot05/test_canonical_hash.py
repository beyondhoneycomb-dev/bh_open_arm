"""Canonical hash determinism — WP-BOOT-05 acceptance ⑥."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from registry.contracts.canonical import canonical_form, canonical_hash, load_schema
from tests.boot05.conftest import schema_with, with_optional_field

BASE = schema_with("camera_id", "capture_ts")

# Each mutation changes one token of normative content. Every one must move the
# hash, otherwise a real schema change could ride under a frozen generation.
CONTENT_MUTATIONS: list[tuple[str, dict[str, Any]]] = [
    (
        "field renamed",
        {"properties": {"camera_id": {"type": "string"}, "capture_t": {"type": "string"}}},
    ),
    (
        "type widened",
        {"properties": {"camera_id": {"type": "string"}, "capture_ts": {"type": "number"}}},
    ),
    ("required relaxed", {"required": ["camera_id"]}),
    ("additional properties opened", {"additionalProperties": True}),
    ("schema dialect changed", {"$schema": "https://json-schema.org/draft-07/schema"}),
]


def test_same_content_yields_same_hash() -> None:
    """A separately constructed but identical schema hashes identically."""
    assert canonical_hash(BASE) == canonical_hash(schema_with("camera_id", "capture_ts"))


def test_key_order_does_not_affect_the_hash() -> None:
    """Serialization order is not content — the projection sorts keys."""
    shuffled = dict(reversed(list(BASE.items())))
    assert canonical_hash(shuffled) == canonical_hash(BASE)


@pytest.mark.parametrize(("label", "mutation"), CONTENT_MUTATIONS, ids=lambda value: str(value))
def test_content_change_changes_the_hash(label: str, mutation: dict[str, Any]) -> None:
    """Any change to normative content moves the hash (acceptance ⑥)."""
    mutated = copy.deepcopy(BASE)
    mutated.update(copy.deepcopy(mutation))
    assert canonical_hash(mutated) != canonical_hash(BASE), label


def test_single_character_change_changes_the_hash() -> None:
    """One character in one field name is enough to break equality."""
    mutated = copy.deepcopy(BASE)
    mutated["properties"]["camera_ie"] = mutated["properties"].pop("camera_id")
    assert canonical_hash(mutated) != canonical_hash(BASE)


def test_optional_field_addition_changes_the_hash() -> None:
    """An optional field is content, so it moves the hash like any other."""
    extended = with_optional_field(BASE, "vendor_hint")
    assert canonical_hash(extended) != canonical_hash(BASE)


def test_annotation_only_edit_preserves_the_hash() -> None:
    """Prose is not content — `06` §4.3 keeps the generation on a doc edit.

    This is the half of the rule that a byte hash would get wrong, turning
    every description fix into a freeze violation and teaching people not to
    freeze.
    """
    annotated = copy.deepcopy(BASE)
    annotated["title"] = "Capture contract"
    annotated["description"] = "Sidecar written next to every captured frame."
    annotated["examples"] = [{"camera_id": "cam0", "capture_ts": "12345"}]
    annotated["properties"]["camera_id"]["description"] = "Stable per-device identifier."
    annotated["properties"]["camera_id"]["$comment"] = "See CTR-PRIM@v1."
    assert canonical_hash(annotated) == canonical_hash(BASE)


def test_field_actually_named_description_is_content() -> None:
    """Annotation stripping must not reach into author-chosen field names.

    A contract may declare a field called `description`; dropping it would make
    a schema that has it hash the same as one that does not.
    """
    with_field = {"type": "object", "properties": {"description": {"type": "string"}}}
    without_field: dict[str, Any] = {"type": "object", "properties": {}}
    assert canonical_hash(with_field) != canonical_hash(without_field)
    assert "description" in canonical_form(with_field)


def test_nested_definitions_are_projected_by_position() -> None:
    """`$defs` keys are names, its values are schemas — both handled."""
    base = {
        "type": "object",
        "$defs": {"title": {"type": "string", "description": "drop me"}},
    }
    renamed = {"type": "object", "$defs": {"titel": {"type": "string"}}}
    stripped = {"type": "object", "$defs": {"title": {"type": "string"}}}
    assert canonical_hash(base) == canonical_hash(stripped)
    assert canonical_hash(base) != canonical_hash(renamed)


def test_array_order_is_content() -> None:
    """Ordered keywords keep their order through the projection."""
    first = {"type": "object", "prefixItems": [{"type": "string"}, {"type": "integer"}]}
    second = {"type": "object", "prefixItems": [{"type": "integer"}, {"type": "string"}]}
    assert canonical_hash(first) != canonical_hash(second)


def test_hash_is_stable_across_processes(tmp_path) -> None:
    """The hash depends on content only, not on dict identity or run order."""
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(BASE), encoding="utf-8")
    assert canonical_hash(load_schema(path)) == canonical_hash(BASE)


def test_hash_carries_its_algorithm() -> None:
    """A future algorithm change is visible rather than silently unequal."""
    assert canonical_hash(BASE).startswith("sha256:")
