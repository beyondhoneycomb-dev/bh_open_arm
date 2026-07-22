"""The CTR-REC@v1 freeze lock — the reverify hook, now that WP-3A-06 has frozen it.

`CTR-REC@v1` is a file-glob contract frozen by the content hash of its canonical
body `contracts/recorder/schema.json` (`06` §3.2). `WP-3A-05` authored the body and
left the contract DRAFT (no ledger append — `WP-3A-06` froze the five consumers
sequentially to avoid a chained-append race); `WP-3A-06` materialised the body and
locked it, so CI-09 now reads the on-disk glob as an intact lock (`06` §4.3).

Beyond the committed-tree check, this test stands the freeze up in a scratch tree:
it materialises the body from `frozen_json_text()`, freezes CTR-REC there at that
body's content hash, and proves CI-09 both accepts the matching bytes and fires on a
one-byte drift. A lock that only ever recomputes the current hash would always match
and be a forge, so the drift case is the one that proves the freeze means something.
"""

from __future__ import annotations

import json
from pathlib import Path

import contracts.recorder as rec
from registry.checks import ci_09
from registry.checks.corpus import Corpus
from registry.checks.fixtures import corpus, record

REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN_GLOB = "contracts/recorder/schema.json"
AUTHORITY = "registry/contracts/contract_index.json"
CONTRACT_ID = "CTR-REC@v1"


def _scratch_corpus(root: Path, body: bytes, frozen_hash: str) -> Corpus:
    """Freeze CTR-REC at a given hash over a scratch tree carrying `body`.

    Args:
        root: Scratch repository root.
        body: The bytes written to the frozen glob.
        frozen_hash: The canonical_hash the authority records as FROZEN.

    Returns:
        (Corpus) A corpus CI-09 can run against without touching the real tree.
    """
    path = root / FROZEN_GLOB
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    (root / "registry" / "contracts").mkdir(parents=True, exist_ok=True)
    authority = {
        "contracts": [
            {"contract_id": CONTRACT_ID, "canonical_hash": frozen_hash, "status": "FROZEN"}
        ]
    }
    (root / AUTHORITY).write_text(json.dumps(authority), encoding="utf-8")
    return corpus(
        (
            record(
                wp="WP-3A-05",
                contract={"consumes": ["CTR-PRIM@v1"], "produces": [CONTRACT_ID]},
                owns=[{"glob": FROZEN_GLOB, "mode": "CONTRACT_FROZEN"}],
            ),
        ),
        root=root,
        tracked_files=(FROZEN_GLOB,),
    )


def _body_and_hash(root: Path) -> tuple[bytes, str]:
    """Return the frozen body bytes and the content hash CI-09 would lock for them."""
    body = rec.frozen_json_text().encode("utf-8")
    (root / FROZEN_GLOB).parent.mkdir(parents=True, exist_ok=True)
    (root / FROZEN_GLOB).write_bytes(body)
    frozen_hash = ci_09.content_hash((FROZEN_GLOB,), root)
    return body, frozen_hash


def test_frozen_body_is_present_and_ci09_does_not_flag_ctr_rec() -> None:
    """CTR-REC@v1 is FROZEN: WP-3A-06 materialised the body and locked it, so CI-09 stays green.

    The body is materialised from `frozen_json_text()` and frozen by WP-3A-06; once
    locked, its content hash matches the committed authority, so CI-09 reads the
    `CONTRACT_FROZEN` glob as an intact lock rather than a drift (`06` §4.3).
    """
    frozen = REPO_ROOT / FROZEN_GLOB
    assert frozen.exists()
    assert frozen.read_text(encoding="utf-8") == rec.frozen_json_text()
    flagged = {finding.req_or_wp for finding in ci_09.run(Corpus(REPO_ROOT)).findings}
    assert CONTRACT_ID not in flagged


def test_matching_body_is_green(tmp_path: Path) -> None:
    """With the emitted body and its own content hash, CI-09 passes and hashes it."""
    body, frozen_hash = _body_and_hash(tmp_path / "seed")
    result = ci_09.run(_scratch_corpus(tmp_path / "run", body, frozen_hash))
    assert not result.findings
    assert result.sites == 1


def test_one_byte_drift_fires(tmp_path: Path) -> None:
    """One byte changed under the frozen body moves the hash off frozen: CI-09 must fire."""
    body, frozen_hash = _body_and_hash(tmp_path / "seed")
    result = ci_09.run(_scratch_corpus(tmp_path / "run", body + b" ", frozen_hash))
    assert result.findings, "the frozen recorder body changed and CI-09 stayed green"
    assert all(f.rule_id == "CI-09" for f in result.findings)
    assert "differs from its registered hash" in result.findings[0].reason


def test_body_present_without_a_frozen_hash_is_caught(tmp_path: Path) -> None:
    """A frozen glob with content but no FROZEN hash is a finding — the pending-freeze state.

    This is the designed transient of the 3A fan-out: the consumer materialises the
    body and leaves CTR-REC DRAFT, so CI-09 flags it as a declaration-not-yet-a-lock
    until `WP-3A-06` appends the one FREEZE event that records its hash. The finding
    here is exactly what that freeze clears, and what makes CTR-REC freezable at all.
    """
    root = tmp_path / "run"
    body = rec.frozen_json_text().encode("utf-8")
    path = root / FROZEN_GLOB
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    (root / "registry" / "contracts").mkdir(parents=True, exist_ok=True)
    (root / AUTHORITY).write_text(json.dumps({"contracts": []}), encoding="utf-8")
    built = corpus(
        (
            record(
                wp="WP-3A-05",
                contract={"consumes": ["CTR-PRIM@v1"], "produces": [CONTRACT_ID]},
                owns=[{"glob": FROZEN_GLOB, "mode": "CONTRACT_FROZEN"}],
            ),
        ),
        root=root,
        tracked_files=(FROZEN_GLOB,),
    )
    result = ci_09.run(built)
    assert result.findings
    assert "no FROZEN hash" in result.findings[0].reason
