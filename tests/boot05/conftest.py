"""Shared fixtures for the contract freeze lock.

The canonical contract table is read from the real `docs/plan/01` in every
test: the closed namespace is exactly what this package must not restate, so a
mock catalog here would test a copy instead of the rule. The registry, ledger
and index are per-test temporaries, because freezing is destructive and the
repository's own ledger records real freeze decisions.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from registry.contracts.index import ContractStore

REPO_ROOT = Path(__file__).resolve().parents[2]

# Consumers are chosen to exercise the shapes the axis has to survive: a
# contract with several consumers, one with exactly one, one with none, and a
# `DEFERRED` record that must not be counted as a consumer at all.
MINI_REGISTRY: dict[str, Any] = {
    "version": 1,
    "spine_ref": "tests/boot05",
    "entries": [
        {"req": "FR-SYS-014", "wp": "WP-0C-01", "contract": {"consumes": ["CTR-PLUG@v1"]}},
        {"req": "FR-SYS-015", "wp": "WP-0C-05", "contract": {"consumes": ["CTR-PLUG@v1"]}},
        {"req": "FR-SYS-016", "wp": "WP-1-02", "contract": {"consumes": ["CTR-PLUG@v1"]}},
        {
            "req": "FR-CON-064",
            "wp": "WP-1-03",
            "contract": {"consumes": ["CTR-ACT@v1", "CTR-CAL@v1"]},
        },
        {"req": "FR-GUI-040", "wp": "WP-G-01", "contract": {"consumes": ["CTR-WS@v1"]}},
        {"req": "FR-GUI-041", "wp": "DEFERRED", "contract": {"consumes": ["CTR-WS@v1"]}},
    ],
}

PLUG_CONSUMERS = ("WP-0C-01", "WP-0C-05", "WP-1-02")


def schema_with(*field_names: str) -> dict[str, Any]:
    """Build a contract schema declaring the named required fields.

    Args:
        *field_names: Field names to declare, all of type string and required.

    Returns:
        dict[str, Any]: A JSON-Schema-shaped contract body.
    """
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {name: {"type": "string"} for name in field_names},
        "required": list(field_names),
        "additionalProperties": False,
    }


def with_optional_field(schema: dict[str, Any], field_name: str) -> dict[str, Any]:
    """Add a field that is *not* required — the exemption that does not exist.

    `06` §4.3 removed the optional-field carve-out deliberately: two schemas
    sharing one version token make "which one did I implement against?"
    unanswerable. This builds the fixture that must still be rejected.

    Args:
        schema: Schema to extend.
        field_name: Name of the optional field to add.

    Returns:
        dict[str, Any]: A copy carrying the extra optional field.
    """
    extended = copy.deepcopy(schema)
    extended["properties"][field_name] = {"type": "string"}
    return extended


def rewrite_registry(store: ContractStore, entries: list[dict[str, Any]]) -> None:
    """Replace the store's registry contents.

    Lets a test move consumers onto a new generation the way the replacement
    work packages do when they land, so trigger fan-out can be checked against
    a registry that changed after a freeze rather than only against a static
    one.

    Args:
        store: Store whose registry file is rewritten.
        entries: Replacement `entries` list.
    """
    document = {"version": 1, "spine_ref": "tests/boot05", "entries": entries}
    store.registry_path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")


@pytest.fixture
def store(tmp_path: Path) -> ContractStore:
    """Provide a contract store over a temporary registry, ledger and index.

    Args:
        tmp_path: Pytest-provided temporary directory.

    Returns:
        ContractStore: Store whose catalog is real and whose state is scratch.
    """
    registry_path = tmp_path / "traceability.yaml"
    registry_path.write_text(yaml.safe_dump(MINI_REGISTRY, allow_unicode=True), encoding="utf-8")
    return ContractStore(
        plan_root=REPO_ROOT,
        registry_path=registry_path,
        ledger_path=tmp_path / "freeze_ledger.yaml",
        index_path=tmp_path / "contract_index.json",
    )
