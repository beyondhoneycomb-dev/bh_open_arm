"""Acceptance ① — the normalization hash is deterministic on settled content.

Same content hashes the same; one changed settled value hashes differently; a
purely cosmetic edit (reordered keys) does not move it. The hash is taken over the
ledger joined to the gate map, so a change to either input must move it.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from registry.normalization.content_hash import (
    HASH_PREFIX,
    ISSUED_PATH,
    canonical_form,
    issue,
    normalization_hash,
    read_issued,
    render_issued_file,
    write_issued,
)
from registry.normalization.gate_map import GATE_MAP_PATH, load_gate_map
from registry.normalization.loader import LEDGER_PATH, load_ledger

_HASH_LEN = len(HASH_PREFIX) + 64


@pytest.fixture(scope="module")
def ledger_document() -> dict[str, Any]:
    """Load the real contradiction ledger."""
    return load_ledger(LEDGER_PATH)


@pytest.fixture(scope="module")
def map_document() -> dict[str, Any]:
    """Load the real gate ID namespace mapping."""
    return load_gate_map(GATE_MAP_PATH)


def test_hash_is_well_formed(ledger_document: dict[str, Any], map_document: dict[str, Any]) -> None:
    """The issued hash is a `sha256:<hex>` token of the fixed length."""
    digest = normalization_hash(ledger_document, map_document)
    assert digest.startswith(HASH_PREFIX)
    assert len(digest) == _HASH_LEN
    assert digest == digest.lower()


def test_same_content_same_hash(
    ledger_document: dict[str, Any], map_document: dict[str, Any]
) -> None:
    """Determinism: recomputing over identical content yields the identical hash."""
    first = normalization_hash(ledger_document, map_document)
    second = normalization_hash(copy.deepcopy(ledger_document), copy.deepcopy(map_document))
    assert first == second


def test_one_row_change_flips_the_hash(
    ledger_document: dict[str, Any], map_document: dict[str, Any]
) -> None:
    """A single changed settled value moves the hash (the bump of acceptance ③)."""
    baseline = normalization_hash(ledger_document, map_document)
    mutated = copy.deepcopy(ledger_document)
    mutated["rows"][0]["winners"][0] = "FR-XXX-999"
    assert normalization_hash(mutated, map_document) != baseline


def test_gate_map_change_flips_the_hash(
    ledger_document: dict[str, Any], map_document: dict[str, Any]
) -> None:
    """The map is an input too: a changed mapping row moves the hash."""
    baseline = normalization_hash(ledger_document, map_document)
    mutated = copy.deepcopy(map_document)
    mutated["rows"][0]["pg_id"] = "PG-XXX-999"
    assert normalization_hash(ledger_document, mutated) != baseline


def test_key_reorder_does_not_move_the_hash(
    ledger_document: dict[str, Any], map_document: dict[str, Any]
) -> None:
    """Canonical form: a semantically identical edit (key order) keeps the hash."""
    baseline = normalization_hash(ledger_document, map_document)
    reordered = {key: ledger_document[key] for key in reversed(list(ledger_document))}
    assert normalization_hash(reordered, map_document) == baseline


def test_canonical_form_sorts_keys(
    ledger_document: dict[str, Any], map_document: dict[str, Any]
) -> None:
    """The serialization the hash is taken over is order-independent text."""
    forward = canonical_form(ledger_document, map_document)
    reordered = {key: ledger_document[key] for key in reversed(list(ledger_document))}
    assert canonical_form(reordered, map_document) == forward


def test_issued_matches_the_published_file() -> None:
    """The committed publication file carries the hash of the real corpus."""
    assert read_issued(ISSUED_PATH) == issue(LEDGER_PATH, GATE_MAP_PATH)


def test_publication_round_trips(tmp_path: Path) -> None:
    """write_issued then read_issued recovers the same token past the header."""
    digest = "sha256:" + "a" * 64
    path = tmp_path / "normalization_hash"
    write_issued(path, digest)
    assert read_issued(path) == digest
    assert render_issued_file(digest).endswith(f"{digest}\n")


def test_read_issued_is_none_when_absent(tmp_path: Path) -> None:
    """A missing publication file reads as no hash, not an error."""
    assert read_issued(tmp_path / "missing") is None


def test_missing_gate_map_still_hashes(tmp_path: Path) -> None:
    """A ledger with no map present hashes deterministically on the ledger alone."""
    first = issue(LEDGER_PATH, tmp_path / "absent_map.yaml")
    second = issue(LEDGER_PATH, tmp_path / "absent_map.yaml")
    assert first == second
    assert first != issue(LEDGER_PATH, GATE_MAP_PATH)
