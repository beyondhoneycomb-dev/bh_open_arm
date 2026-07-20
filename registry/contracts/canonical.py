"""Canonical form and content hash of a contract schema.

The hash answers exactly one question: is this the contract the consumers were
spawned against. `06` §4.3 fixes what that means, and it is not byte equality —
the same table that makes *any* field addition a `@v(n+1)` event, optional
fields included, also declares a documentation-, comment- or example-only edit
to leave the schema hash unchanged and the generation intact.

So the hash is taken over a projection that drops annotation keywords. Hashing
raw bytes would satisfy the first half and break the second: every typo fix in
a `description` would become a freeze violation, and the correct response to a
checker that fires on lawful edits is for people to stop freezing contracts.

The projection is deliberately structural rather than semantic. It does not
canonicalize `required` ordering or resolve `$ref`, because a contract whose
field set is unchanged but whose text moved is still one the tooling should
force a human to look at; only the four annotation keywords are provably
non-normative.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

HASH_ALGORITHM = "sha256"

# Keywords whose value is prose about the schema rather than part of it. The
# set is closed by `06` §4.3, whose hash-invariant row covers documentation,
# comments and examples only; adding to it here would silently widen what may
# change underneath a frozen generation.
ANNOTATION_KEYWORDS = frozenset({"description", "title", "$comment", "examples", "example"})

# Keywords whose value is a map from *author-chosen field names* to schemas.
# Annotation stripping must not descend into these keys as if they were
# keywords: a contract may legitimately declare a field named `description`,
# and dropping it would make two different contracts hash identically.
NAME_MAP_KEYWORDS = frozenset({"properties", "$defs", "definitions", "patternProperties"})


def canonical_form(schema: Mapping[str, Any]) -> str:
    """Render the normative projection of a schema as deterministic text.

    Args:
        schema: Parsed contract schema.

    Returns:
        str: Compact JSON with object keys sorted, annotations removed, and
            array order preserved.
    """
    projected = _project_schema(schema)
    return json.dumps(projected, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_hash(schema: Mapping[str, Any]) -> str:
    """Compute the content hash a freeze locks the contract to.

    Args:
        schema: Parsed contract schema.

    Returns:
        str: Hash as `sha256:<hex>`. The algorithm is carried in the value so a
            future change of algorithm is visible in the index instead of
            silently comparing unequal digests.
    """
    digest = hashlib.sha256(canonical_form(schema).encode("utf-8")).hexdigest()
    return f"{HASH_ALGORITHM}:{digest}"


def load_schema(path: Path) -> dict[str, Any]:
    """Read a contract schema from a JSON document.

    Args:
        path: Path to the schema file.

    Returns:
        dict[str, Any]: The parsed schema.

    Raises:
        TypeError: If the document is not a JSON object.
    """
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise TypeError(f"{path}: contract schema must be a JSON object, found {type(parsed)}")
    return parsed


def _project_schema(node: Any) -> Any:
    """Drop annotation keywords from a node interpreted as a schema.

    Args:
        node: Schema, list of schemas, or scalar.

    Returns:
        Any: The node with annotation keywords removed at every schema level.
    """
    if isinstance(node, Mapping):
        projected: dict[Any, Any] = {}
        for key, value in node.items():
            if key in ANNOTATION_KEYWORDS:
                continue
            if key in NAME_MAP_KEYWORDS:
                projected[key] = _project_name_map(value)
            else:
                projected[key] = _project_schema(value)
        return projected
    if isinstance(node, list):
        return [_project_schema(item) for item in node]
    return node


def _project_name_map(node: Any) -> Any:
    """Project a map whose keys are author-chosen field names.

    Args:
        node: Mapping from field name to schema, or any other node.

    Returns:
        Any: The mapping with every key preserved and every value projected.
    """
    if isinstance(node, Mapping):
        return {key: _project_schema(value) for key, value in node.items()}
    return _project_schema(node)
