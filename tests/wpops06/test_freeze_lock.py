"""The CTR-ERR freeze lock, end to end: a real freeze, and drift that fires.

CTR-ERR is a file-glob contract (06 §3.2), frozen by the byte-exact content hash of
`contracts/errors/error_registry.yaml`. The locked value lives once in the committed
freeze authority (`registry/contracts/contract_index.json`), recorded by a FREEZE
event, and CI-09 reads it there and compares it to the file on disk.

The separating test is the last: a lock that only recomputes the current hash would
always match and would be a forge. Mutating one byte must make CI-09 fire. This
mirrors the committed CTR-UNIT@v1 drift test (tests/boot05).

The generation is resolved from the authority rather than written here. `06` §4.3
makes `@v(n+1)` the prescribed response to any change under a frozen glob, so a
literal `@v1` in this file would make every legitimate bump look like a broken test
— and the fix would be to edit the literal, which teaches exactly the wrong reflex
about a lock whose whole job is to notice change.
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
CONTRACT_NAME = "CTR-ERR"


def _frozen_generation() -> tuple[str, str]:
    """Find the live frozen generation of CTR-ERR and the hash it locked.

    Returns:
        (tuple[str, str]) The contract id and its recorded `canonical_hash`.
    """
    index = json.loads((REPO_ROOT / AUTHORITY).read_text(encoding="utf-8"))
    frozen = [
        row
        for row in index["contracts"]
        if str(row["contract_id"]).startswith(f"{CONTRACT_NAME}@v") and row["status"] == "FROZEN"
    ]
    assert len(frozen) == 1, (
        f"exactly one {CONTRACT_NAME} generation may be FROZEN at a time; "
        f"found {[r['contract_id'] for r in frozen]}"
    )
    return str(frozen[0]["contract_id"]), str(frozen[0]["canonical_hash"])


def _committed_frozen_hash() -> str:
    """Read the live frozen generation's locked hash from the committed authority.

    Returns:
        (str) The `canonical_hash` the FROZEN generation recorded.
    """
    return _frozen_generation()[1]


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
    contract_id = _frozen_generation()[0]
    (root / "registry" / "contracts").mkdir(parents=True, exist_ok=True)
    authority = {
        "contracts": [
            {"contract_id": contract_id, "canonical_hash": frozen_hash, "status": "FROZEN"}
        ]
    }
    (root / AUTHORITY).write_text(json.dumps(authority), encoding="utf-8")
    return corpus(
        (
            record(
                wp="WP-OPS-06",
                contract={"consumes": [], "produces": [contract_id]},
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


def test_a_moved_frozen_file_does_not_silently_disarm_its_lock(tmp_path: Path) -> None:
    """A frozen glob that matches nothing must fire, not be skipped.

    Renaming or moving a frozen file without updating its `owns[]` glob leaves the
    recorded hash guarding an empty file set. Skipping that case reports green while
    the frozen body has become freely editable — the lock is gone and the only check
    that would notice has stopped looking. This is not hypothetical here: one commit
    this session moved two documentation directories and broke roughly twenty path
    constants, and the same move applied to a contract glob produces silence.
    """
    contract_id, frozen_hash = _frozen_generation()
    (tmp_path / "registry" / "contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / AUTHORITY).write_text(
        json.dumps(
            {
                "contracts": [
                    {
                        "contract_id": contract_id,
                        "canonical_hash": frozen_hash,
                        "status": "FROZEN",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    moved_away = corpus(
        (
            record(
                wp="WP-OPS-06",
                contract={"consumes": [], "produces": [contract_id]},
                owns=[{"glob": "contracts/errors/moved_away.yaml", "mode": "CONTRACT_FROZEN"}],
            ),
        ),
        root=tmp_path,
        tracked_files=("registry/traceability.yaml",),
    )

    result = ci_09.run(moved_away)

    assert result.findings, "the frozen glob matched nothing and CI-09 stayed green"
    assert "guards nothing" in result.findings[0].reason
    assert result.sites == 1, "a disarmed lock must be counted, not reported as vacuous"
