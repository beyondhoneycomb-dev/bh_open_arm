"""The real ledger is schema-valid and every claim it makes holds on the corpus.

Acceptance `02a` §1.5 WP-N1-01 ①–③ and WP-N1-02 ①–④: the ledger validates, every
winner resolves to a single definition, every discarded quote is present, and no
winner contradicts a SPINE invariant (encoded here as: the rulings load and
validate as a set, and the six contradictions are all present).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from registry.normalization.loader import schema_errors
from registry.normalization.validator import Corpus, validate

EXPECTED_ROWS = {"NORM-001", "NORM-002", "NORM-003", "NORM-004", "NORM-006", "NORM-007"}
EXPECTED_NOTE = "NORM-005"


def test_ledger_matches_schema(ledger: dict[str, Any]) -> None:
    """The ledger satisfies its JSON Schema."""
    assert schema_errors(ledger) == []


def test_ledger_loads_the_six_contradictions(ledger: dict[str, Any]) -> None:
    """All six §1.3 rulings are present, and none is duplicated."""
    ids = [row["norm_id"] for row in ledger["rows"]]
    assert set(ids) == EXPECTED_ROWS
    assert len(ids) == len(EXPECTED_ROWS)


def test_norm_005_is_a_note_not_a_row(ledger: dict[str, Any]) -> None:
    """NORM-005 is the §1.4 reference-integrity note, not a contradiction row."""
    row_ids = {row["norm_id"] for row in ledger["rows"]}
    note_ids = {note["norm_id"] for note in ledger.get("notes", [])}
    assert EXPECTED_NOTE not in row_ids
    assert EXPECTED_NOTE in note_ids


def test_norm_005_resolution_cites_the_real_source(ledger: dict[str, Any]) -> None:
    """The note replaces the nonexistent 16 M-25 citation with the real sources."""
    note = next(note for note in ledger["notes"] if note["norm_id"] == EXPECTED_NOTE)
    assert "M-25" in note["finding"]
    for citation in ("15 §2.10", "15 §2.1", "01 NFR-SYS-002"):
        assert citation in note["resolution"]


def test_every_winner_is_a_non_empty_list(ledger: dict[str, Any]) -> None:
    """The schema decision: a winner field is a non-empty list, not a scalar."""
    for row in ledger["rows"]:
        assert isinstance(row["winners"], list)
        assert len(row["winners"]) >= 1


def test_multi_winner_rows_are_present(ledger: dict[str, Any]) -> None:
    """Four rulings win more than one id; a scalar field could not carry them."""
    multi = {row["norm_id"] for row in ledger["rows"] if len(row["winners"]) > 1}
    assert {"NORM-001", "NORM-002", "NORM-003", "NORM-004"} <= multi


def test_ledger_claims_hold_on_the_corpus(ledger: dict[str, Any], repo_root: Path) -> None:
    """Winners resolve, discarded quotes are present, enforcement checks exist."""
    corpus = Corpus.load(repo_root)
    assert [violation.as_line() for violation in validate(corpus, ledger)] == []
