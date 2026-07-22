"""WP-3A-04 — the reverify/freeze-drift hook: CTR-WS@v1, now frozen by WP-3A-06.

CTR-WS@v1 is a file-glob contract frozen by the byte-exact content hash of
`contracts/ws/envelope.schema.json`. `WP-3A-04` authored the typed source and left the
contract DRAFT (appending to the chained ledger would have raced the parallel 3A
freezes); `WP-3A-06` materialised the body from `envelope_json()` and froze it in
sequence.

What this proves: the generated body is self-consistent (the reverify hook), the
committed authority now shows CTR-WS FROZEN with its content hash locked, the frozen
body on disk equals the generator, and the CI-09 lock fires on a one-byte drift —
proven against a scratch tree. A lock that only ever recomputes the current hash would
always match and would be a forge.
"""

from __future__ import annotations

import json
from pathlib import Path

import contracts.ws as ws
from contracts.ws.reverify import ENVELOPE_PATH
from registry.checks import ci_09
from registry.checks.fixtures import corpus, record

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = "registry/contracts/contract_index.json"
FROZEN_GLOB = "contracts/ws/envelope.schema.json"
CONTRACT_ID = "CTR-WS@v1"


def test_ctr_ws_is_frozen_in_the_committed_authority() -> None:
    """WP-3A-06 appended the CTR-WS freeze; the authority now carries it FROZEN with its hash."""
    index = json.loads((REPO_ROOT / AUTHORITY).read_text(encoding="utf-8"))
    row = next(r for r in index["contracts"] if r["contract_id"] == CONTRACT_ID)
    assert row["status"] == "FROZEN"
    assert row["canonical_hash"] is not None
    assert row["owner_wp"] == "WP-3A-04"


def test_frozen_body_is_present_and_matches_the_generator() -> None:
    """After the freeze the envelope body is on disk and equals `envelope_json()`."""
    assert ENVELOPE_PATH.exists()
    assert (REPO_ROOT / FROZEN_GLOB).exists()
    assert ENVELOPE_PATH.read_text(encoding="utf-8") == ws.envelope_json()


def test_reverify_confirms_the_generated_body() -> None:
    """The reverify hook confirms the generated body against CTR-PRIM@v1 and the mirror."""
    report = ws.reverify()
    assert report.confirmed, report.mismatches


def test_ci_09_raises_no_finding_against_ctr_ws() -> None:
    """CI-09 never fires on CTR-WS: its frozen body is absent, so it is a clean DRAFT.

    The whole-tree CI-09 result is not asserted green here on purpose — a concurrent
    3A sibling that has already written its own frozen body while still DRAFT would
    make it fire on *that* contract, which is not this WP's business. What this WP
    owns is that CTR-WS contributes no such finding.
    """
    from registry.checks.corpus import Corpus

    result = ci_09.run(Corpus(REPO_ROOT))
    assert all(finding.req_or_wp != CONTRACT_ID for finding in result.findings)


def _scratch_corpus(root: Path, body: bytes, frozen_hash: str | None) -> object:
    """Build a scratch corpus that freezes CTR-WS at a given hash (or leaves it DRAFT).

    Args:
        root: Scratch repository root.
        body: The frozen body bytes to place on disk.
        frozen_hash: The hash to register as FROZEN, or None to leave CTR-WS unfrozen.

    Returns:
        (object) A corpus CI-09 can run against without touching the real tree.
    """
    path = root / FROZEN_GLOB
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    (root / "registry" / "contracts").mkdir(parents=True, exist_ok=True)
    contracts_rows = (
        [{"contract_id": CONTRACT_ID, "canonical_hash": frozen_hash, "status": "FROZEN"}]
        if frozen_hash is not None
        else []
    )
    (root / AUTHORITY).write_text(json.dumps({"contracts": contracts_rows}), encoding="utf-8")
    return corpus(
        (
            record(
                wp="WP-3A-04",
                contract={"consumes": ["CTR-PRIM@v1"], "produces": [CONTRACT_ID]},
                owns=[{"glob": FROZEN_GLOB, "mode": "CONTRACT_FROZEN"}],
            ),
        ),
        root=root,
        tracked_files=(FROZEN_GLOB,),
    )


def test_matching_content_is_green(tmp_path: Path) -> None:
    """With the generated body and its own content hash registered FROZEN, CI-09 passes."""
    body = ws.envelope_json().encode("utf-8")
    # Place the body, then lock exactly the hash CI-09 will recompute (never a re-hash).
    _scratch_corpus(tmp_path, body, None)
    frozen_hash = ci_09.content_hash((FROZEN_GLOB,), tmp_path)
    result = ci_09.run(_scratch_corpus(tmp_path, body, frozen_hash))
    assert not result.findings
    assert result.sites == 1


def test_one_byte_drift_fires(tmp_path: Path) -> None:
    """One extra byte under the frozen body moves the content hash off frozen: CI-09 must fire."""
    body = ws.envelope_json().encode("utf-8")
    _scratch_corpus(tmp_path, body, None)
    frozen_hash = ci_09.content_hash((FROZEN_GLOB,), tmp_path)
    result = ci_09.run(_scratch_corpus(tmp_path, body + b" ", frozen_hash))
    assert result.findings, "a byte changed under the frozen envelope and CI-09 stayed green"
    assert all(f.rule_id == "CI-09" for f in result.findings)
    assert "differs from its registered hash" in result.findings[0].reason


def test_content_without_a_frozen_hash_fires(tmp_path: Path) -> None:
    """The DRAFT-with-content state this WP avoids: a frozen body but no registered hash fires."""
    body = ws.envelope_json().encode("utf-8")
    result = ci_09.run(_scratch_corpus(tmp_path, body, None))
    assert result.findings
    assert "no FROZEN hash" in result.findings[0].reason
