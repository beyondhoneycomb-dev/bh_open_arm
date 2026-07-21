"""The CTR-ERR@v1 freeze lock, end to end: a real freeze, and drift that fires.

CTR-ERR@v1 is a file-glob contract (06 §3.2), frozen by the byte-exact content
hash of `contracts/errors/error_registry.yaml`. The locked value lives once in the
committed freeze authority (`registry/contracts/contract_index.json`), recorded by
a FREEZE event, and CI-09 reads it there and compares it to the file on disk.

The separating test is the last: a lock that only recomputes the current hash
would always match and would be a forge. Mutating one byte must make CI-09 fire.
This mirrors the committed CTR-UNIT@v1 drift test (tests/boot05).
"""

from __future__ import annotations

import json
from pathlib import Path

from registry.checks import ci_09
from registry.checks.corpus import Corpus
from registry.checks.fixtures import corpus, record

REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN_GLOB = "contracts/errors/error_registry.yaml"
AUTHORITY = "registry/contracts/contract_index.json"
CONTRACT_ID = "CTR-ERR@v1"


def _committed_frozen_hash() -> str:
    """Read CTR-ERR@v1's locked hash from the committed freeze authority.

    Returns:
        (str) The `canonical_hash` the FROZEN generation recorded.
    """
    index = json.loads((REPO_ROOT / AUTHORITY).read_text(encoding="utf-8"))
    row = next(r for r in index["contracts"] if r["contract_id"] == CONTRACT_ID)
    assert row["status"] == "FROZEN", "CTR-ERR@v1 must be FROZEN in the committed authority"
    return str(row["canonical_hash"])


def _scratch_corpus(root: Path, registry_bytes: bytes, frozen_hash: str) -> Corpus:
    """Build a corpus over a scratch tree that freezes CTR-ERR at a given hash.

    Args:
        root: Scratch repository root.
        registry_bytes: Bytes to write at the frozen glob path.
        frozen_hash: The canonical_hash the authority records as FROZEN.

    Returns:
        (Corpus) A corpus CI-09 can run against without touching the real tree.
    """
    (root / "contracts" / "errors").mkdir(parents=True, exist_ok=True)
    (root / FROZEN_GLOB).write_bytes(registry_bytes)
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
                wp="WP-OPS-06",
                contract={"consumes": [], "produces": [CONTRACT_ID]},
                owns=[{"glob": FROZEN_GLOB, "mode": "CONTRACT_FROZEN"}],
            ),
        ),
        root=root,
        tracked_files=(FROZEN_GLOB,),
    )


def test_committed_freeze_is_the_files_content_hash() -> None:
    """The locked hash is exactly CI-09's own hash of the file, not a drifted copy."""
    assert _committed_frozen_hash() == ci_09.content_hash((FROZEN_GLOB,), REPO_ROOT)


def test_real_repo_is_green_and_actually_hashed() -> None:
    """Against the real tree CI-09 finds no drift, and CTR-ERR was hashed, not skipped."""
    result = ci_09.run(Corpus(REPO_ROOT))
    assert not result.findings
    assert result.sites >= 1


def test_matching_content_is_green(tmp_path: Path) -> None:
    """With the committed bytes and the committed hash, CI-09 passes."""
    real = (REPO_ROOT / FROZEN_GLOB).read_bytes()
    result = ci_09.run(_scratch_corpus(tmp_path, real, _committed_frozen_hash()))
    assert not result.findings
    assert result.sites == 1


def test_one_byte_drift_fires(tmp_path: Path) -> None:
    """One extra byte moves the content hash off the frozen value: CI-09 must fire."""
    mutated = (REPO_ROOT / FROZEN_GLOB).read_bytes() + b" "
    result = ci_09.run(_scratch_corpus(tmp_path, mutated, _committed_frozen_hash()))
    assert result.findings, "a byte changed under a frozen contract and CI-09 stayed green"
    assert all(f.rule_id == "CI-09" for f in result.findings)
    assert "differs from its registered hash" in result.findings[0].reason
