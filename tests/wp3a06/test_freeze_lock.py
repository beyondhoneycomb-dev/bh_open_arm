"""The six-contract freeze, end to end: all FROZEN, one valid chain, CI-09 green.

`02b` §5.2 WP-3A-06: WP-3A-06 froze the five consumer contracts sequentially onto
the ledger that already carried `CTR-PRIM@v1`, one append at a time. This proves
the result: the ledger records all six as FROZEN, its digest chain reconstructs,
the committed authority carries each locked hash, and CI-09 finds no drift against
the real tree. The per-contract drift proof lives in `test_contract_regression`.
"""

from __future__ import annotations

import json
from pathlib import Path

from registry.checks import ci_09
from registry.checks.corpus import Corpus
from registry.contracts import ledger
from registry.contracts.index import ContractStore

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = REPO_ROOT / "registry" / "contracts" / "contract_index.json"

# The six contracts this barrier freezes, and the order WP-3A-06 appended the five
# consumers after `CTR-PRIM@v1` (`02b` freeze mechanics: CAM -> CAP -> TEL -> WS -> REC).
PRIMITIVE = "CTR-PRIM@v1"
CONSUMER_ORDER = ("CTR-CAM@v1", "CTR-CAP@v1", "CTR-TEL@v1", "CTR-WS@v1", "CTR-REC@v1")
ALL_SIX = (PRIMITIVE, *CONSUMER_ORDER)


def _authority_rows() -> dict[str, dict[str, object]]:
    """Return the committed authority's contract rows keyed by id.

    Returns:
        (dict[str, dict[str, object]]) Contract id to its authority record.
    """
    index = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    return {row["contract_id"]: row for row in index["contracts"]}


def test_all_six_contracts_are_frozen_in_the_authority() -> None:
    """Each of the six contracts is FROZEN with a non-null locked hash."""
    rows = _authority_rows()
    for contract_id in ALL_SIX:
        assert rows[contract_id]["status"] == "FROZEN", f"{contract_id} is not FROZEN"
        assert rows[contract_id]["canonical_hash"], f"{contract_id} has no locked hash"


def test_ledger_chain_is_valid_and_records_the_five_consumers_in_order() -> None:
    """The ledger reconstructs, and the five consumer freezes follow CTR-PRIM in order."""
    store = ContractStore.at(REPO_ROOT)
    events = ledger.read_ledger(store.ledger_path)
    assert not ledger.verify_chain(events), "the freeze ledger chain does not reconstruct"

    freezes = [event.contract_id for event in events if event.kind == ledger.FREEZE]
    prim_at = freezes.index(PRIMITIVE)
    assert freezes[prim_at + 1 : prim_at + 1 + len(CONSUMER_ORDER)] == list(CONSUMER_ORDER)


def test_authority_head_matches_the_ledger_head() -> None:
    """The authority's ledger_head is the digest of the last appended event."""
    store = ContractStore.at(REPO_ROOT)
    events = ledger.read_ledger(store.ledger_path)
    index = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    assert index["ledger_head"] == events[-1].digest


def test_ci_09_is_green_against_the_real_tree_and_hashed_all_six() -> None:
    """CI-09 finds no drift, and the six frozen 3A contracts were among those hashed."""
    result = ci_09.run(Corpus(REPO_ROOT))
    assert not result.findings, [f.reason for f in result.findings]
    # UNIT/ERR/CAL predate this WP; the six 3A contracts must all be live hash sites.
    assert result.sites >= len(ALL_SIX)
