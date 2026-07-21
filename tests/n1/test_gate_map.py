"""The gate ID namespace mapping is schema-valid and corpus-honest.

These tests hold the `WP-N1-03` acceptance criteria: every `03` gate has exactly
one mapping row (①), every `spec_ref` resolves so no dangling reference survives
(②), and the schema refuses the ghost id `M-25`, the sealed id `M-8`, and the
unsplit `PG-RT-001` (the seal at the reference and gate positions).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from registry.normalization import gate_map
from registry.normalization.validator import Corpus

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    """Resolve the corpus once for the module."""
    return Corpus.load(REPO_ROOT)


@pytest.fixture(scope="module")
def real_map() -> dict:
    """Load the shipped gate mapping."""
    return gate_map.load_gate_map(gate_map.GATE_MAP_PATH)


def test_real_map_passes_schema(real_map: dict) -> None:
    """The shipped mapping matches its JSON Schema."""
    assert gate_map.schema_errors(real_map) == []


def test_real_map_is_corpus_honest(corpus: Corpus, real_map: dict) -> None:
    """The shipped mapping makes no claim the corpus does not support."""
    assert [v.as_line() for v in gate_map.validate(corpus, real_map)] == []


def test_map_covers_the_gate_roster_exactly(corpus: Corpus, real_map: dict) -> None:
    """The mapped gate set equals the 03 gate roster, both directions."""
    mapped = {str(row["pg_id"]) for row in real_map["rows"]}
    assert mapped == corpus.gate_roster


def test_pg_can_001_cites_the_norm_005_basis(real_map: dict) -> None:
    """PG-CAN-001 maps to the corrected basis, not the ghost id M-25."""
    row = next(r for r in real_map["rows"] if r["pg_id"] == "PG-CAN-001")
    assert set(row["spec_refs"]) == {"15 §2.10", "15 §2.1", "NFR-SYS-002"}


def test_missing_gate_is_caught(corpus: Corpus) -> None:
    """A mapping that omits a roster gate reports a coverage violation."""
    document = {
        "version": 1,
        "rows": [{"pg_id": "PG-CAN-001", "spec_refs": ["15 §2.1"], "branches": ["PASS"]}],
    }
    kinds = {v.kind for v in gate_map.validate(corpus, document)}
    assert "coverage" in kinds


def test_extra_gate_is_caught(corpus: Corpus, real_map: dict) -> None:
    """A row naming a gate the roster does not declare is a coverage violation."""
    document = {
        "version": 1,
        "rows": list(real_map["rows"])
        + [{"pg_id": "PG-FAKE-001", "spec_refs": ["M-2"], "branches": ["PASS"]}],
    }
    assert any(
        v.pg_id == "PG-FAKE-001" and v.kind == "coverage"
        for v in gate_map.validate(corpus, document)
    )


def test_duplicate_gate_is_caught(corpus: Corpus, real_map: dict) -> None:
    """A gate mapped twice reports a duplicate violation."""
    first = real_map["rows"][0]
    document = {"version": 1, "rows": list(real_map["rows"]) + [dict(first)]}
    assert any(v.kind == "duplicate" for v in gate_map.validate(corpus, document))


def test_dangling_spec_ref_is_caught(corpus: Corpus) -> None:
    """A schema-shaped but undefined FR/NFR id resolves to nothing and is caught."""
    document = {
        "version": 1,
        "rows": [{"pg_id": "PG-VR-001", "spec_refs": ["NFR-PRF-999"], "branches": ["PASS"]}],
    }
    assert any(
        v.kind == "spec_ref" and "NFR-PRF-999" in v.detail
        for v in gate_map.validate(corpus, document)
    )


def test_ghost_id_m25_rejected_by_schema() -> None:
    """M-25 cannot enter the map: the schema pattern excludes it."""
    document = {
        "version": 1,
        "rows": [{"pg_id": "PG-CAN-001", "spec_refs": ["M-25"], "branches": ["PASS"]}],
    }
    assert gate_map.schema_errors(document) != []


def test_sealed_id_m8_rejected_by_schema() -> None:
    """M-8 cannot enter the map as a reference: the schema pattern excludes it."""
    document = {
        "version": 1,
        "rows": [{"pg_id": "PG-RT-001a", "spec_refs": ["M-8"], "branches": ["PASS"]}],
    }
    assert gate_map.schema_errors(document) != []


def test_bare_pg_rt_001_rejected_by_schema() -> None:
    """The unsplit PG-RT-001 cannot be a mapped gate id."""
    document = {
        "version": 1,
        "rows": [{"pg_id": "PG-RT-001", "spec_refs": ["NFR-PRF-054"], "branches": ["PASS"]}],
    }
    assert gate_map.schema_errors(document) != []


def test_invented_branch_rejected_by_schema() -> None:
    """A state outside the fixed five is refused."""
    document = {
        "version": 1,
        "rows": [{"pg_id": "PG-VR-001", "spec_refs": ["M-22"], "branches": ["MAYBE"]}],
    }
    assert gate_map.schema_errors(document) != []
