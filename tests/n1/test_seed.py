"""The seeder hook settles the right records and leaves the rest for CI-07.

`02a` §−2.3 calls a checker that is green while catching nothing the worst
outcome. Stamping every contested record would make `CI-07` exactly that, so this
proves the seeder stamps only ledger-settled records and leaves a genuinely
unsettled `결정필요` record null, where `CI-07` must still fire.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from registry import PLAN_DIR, SPEC_DIR, SPINE_DOC_REL
from registry.ingest.build import build
from registry.normalization.seed import HASH_PREFIX, ledger_seed

TAG_DECISION_REQUIRED = "결정필요"
WP_DEFERRED = "DEFERRED"


def test_settled_ids_include_winners_and_discarded_reqs() -> None:
    """Both a winner and a discarded requirement are settled by the ledger."""
    seed = ledger_seed(PLAN_DIR)
    assert "FR-SAF-075" in seed.settled_ids  # NORM-001 winner
    assert "PG-RT-001a" in seed.settled_ids  # NORM-003 winner
    assert "FR-SAF-045" in seed.settled_ids  # NORM-004 discarded requirement
    assert "FR-GUI-065" in seed.settled_ids  # NORM-006 discarded requirement


def test_digest_is_deterministic_and_well_formed() -> None:
    """The placeholder hash is a stable sha256 over the ledger content."""
    first = ledger_seed(PLAN_DIR).digest
    second = ledger_seed(PLAN_DIR).digest
    assert first is not None
    assert first == second
    assert first.startswith(HASH_PREFIX)
    assert len(first) == len(HASH_PREFIX) + 64


def test_missing_ledger_yields_an_empty_seed(tmp_path: Path) -> None:
    """A directory with no ledger stamps nothing, as at bootstrap."""
    seed = ledger_seed(tmp_path)
    assert seed.settled_ids == frozenset()
    assert seed.digest is None


def test_normalization_for_is_scoped_to_settled_ids() -> None:
    """The hash is offered only for settled requirements."""
    seed = ledger_seed(PLAN_DIR)
    assert seed.normalization_for("FR-SAF-045") == seed.digest
    assert seed.normalization_for("FR-DOES-NOT-EXIST") is None


@pytest.fixture(scope="module")
def seeded_registry() -> dict[str, Any]:
    """Build the registry document from the live corpus."""
    document, _ = build(PLAN_DIR, SPEC_DIR, f"{SPINE_DOC_REL}@0000000")
    return document


def test_settled_records_carry_the_ledger_hash(seeded_registry: dict[str, Any]) -> None:
    """A settled requirement's record is stamped with the ledger hash."""
    digest = ledger_seed(PLAN_DIR).digest
    by_req = {record["req"]: record for record in seeded_registry["entries"]}
    assert by_req["FR-SAF-045"].get("normalization") == digest


def test_no_record_carries_a_foreign_hash(seeded_registry: dict[str, Any]) -> None:
    """Every stamped record carries the one ledger hash, never a second one."""
    digest = ledger_seed(PLAN_DIR).digest
    stamped = {
        record["normalization"]
        for record in seeded_registry["entries"]
        if record.get("normalization")
    }
    assert stamped == {digest}


def test_the_seeder_stamps_only_what_the_ledger_settles() -> None:
    """A requirement the ledger does not settle gets no hash — CI-07 stays non-vacuous.

    Asked of the seeder directly rather than by scanning the registry for a leftover
    undecided record: that phrasing only held while the corpus happened to contain one,
    so ruling on the last contested requirement would silently empty the sample and the
    assertion would pass over nothing. Both directions are pinned here — the seeder does
    stamp what is settled, and does not stamp what is not.
    """
    seed = ledger_seed(PLAN_DIR)

    assert seed.settled_ids, "the ledger settles nothing; the seeder would stamp nothing"
    assert seed.digest is not None
    settled = next(iter(sorted(seed.settled_ids)))
    assert seed.normalization_for(settled) == seed.digest

    unsettled = "FR-XXX-999"
    assert unsettled not in seed.settled_ids
    assert seed.normalization_for(unsettled) is None
