"""The CTR-PRIM@v1 freeze lock, end to end: a real freeze, and drift that fires.

CTR-PRIM@v1 is a file-glob contract (`06` §3.2), frozen by the byte-exact content
hash of its two frozen bodies, `contracts/prim/schema.py` and
`contracts/prim/schema.json`. The locked value lives once in the committed freeze
authority (`registry/contracts/contract_index.json`), recorded by a FREEZE event
in the append-only ledger, and CI-09 reads it there and compares it to the files
on disk. This mirrors the committed CTR-UNIT@v1 / CTR-ERR@v1 drift tests.

The separating test is the last one: a lock that only ever recomputes the current
hash would always match and would be a forge. Mutating one byte of one frozen
body must make CI-09 fire, or the "single definition point" proves nothing — a
consumer could edit a primitive and 3B would fan the split out thirteen ways.
"""

from __future__ import annotations

import json
from pathlib import Path

from registry.checks import ci_09
from registry.checks.corpus import Corpus
from registry.checks.fixtures import corpus, record

REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN_GLOBS = ("contracts/prim/schema.json", "contracts/prim/schema.py")
AUTHORITY = "registry/contracts/contract_index.json"
CONTRACT_ID = "CTR-PRIM@v1"


def _committed_frozen_hash() -> str:
    """Read CTR-PRIM@v1's locked hash from the committed freeze authority.

    Returns:
        (str) The `canonical_hash` the FROZEN generation recorded.
    """
    index = json.loads((REPO_ROOT / AUTHORITY).read_text(encoding="utf-8"))
    row = next(r for r in index["contracts"] if r["contract_id"] == CONTRACT_ID)
    assert row["status"] == "FROZEN", "CTR-PRIM@v1 must be FROZEN in the committed authority"
    return str(row["canonical_hash"])


def _scratch_corpus(root: Path, bodies: dict[str, bytes], frozen_hash: str) -> Corpus:
    """Build a corpus over a scratch tree that freezes CTR-PRIM at a given hash.

    Args:
        root: Scratch repository root.
        bodies: Root-relative path to bytes for each frozen body.
        frozen_hash: The canonical_hash the authority records as FROZEN.

    Returns:
        (Corpus) A corpus CI-09 can run against without touching the real tree.
    """
    for relative, content in bodies.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
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
                wp="WP-3A-00",
                contract={"consumes": [], "produces": [CONTRACT_ID]},
                owns=[{"glob": glob, "mode": "CONTRACT_FROZEN"} for glob in FROZEN_GLOBS],
            ),
        ),
        root=root,
        tracked_files=FROZEN_GLOBS,
    )


def _committed_bodies() -> dict[str, bytes]:
    """Read the committed bytes of both frozen bodies.

    Returns:
        (dict[str, bytes]) Root-relative path to its committed content.
    """
    return {glob: (REPO_ROOT / glob).read_bytes() for glob in FROZEN_GLOBS}


def test_committed_freeze_is_the_files_content_hash() -> None:
    """The locked hash is exactly CI-09's own hash of the frozen bodies, not a drifted copy."""
    assert _committed_frozen_hash() == ci_09.content_hash(FROZEN_GLOBS, REPO_ROOT)


def test_real_repo_is_green_and_actually_hashed() -> None:
    """Against the real tree CI-09 finds no drift, and CTR-PRIM was hashed, not skipped."""
    result = ci_09.run(Corpus(REPO_ROOT))
    assert not result.findings
    assert result.sites >= 1


def test_matching_content_is_green(tmp_path: Path) -> None:
    """With the committed bytes and the committed hash, CI-09 passes."""
    result = ci_09.run(_scratch_corpus(tmp_path, _committed_bodies(), _committed_frozen_hash()))
    assert not result.findings
    assert result.sites == 1


def test_one_byte_drift_in_schema_py_fires(tmp_path: Path) -> None:
    """One extra byte in the Python body moves the content hash off frozen: CI-09 must fire."""
    bodies = _committed_bodies()
    bodies["contracts/prim/schema.py"] += b" "
    result = ci_09.run(_scratch_corpus(tmp_path, bodies, _committed_frozen_hash()))
    assert result.findings, "a byte changed under a frozen primitive and CI-09 stayed green"
    assert all(f.rule_id == "CI-09" for f in result.findings)
    assert "differs from its registered hash" in result.findings[0].reason


def test_one_byte_drift_in_schema_json_fires(tmp_path: Path) -> None:
    """A change to the JSON mirror is drift too: the two bodies are one frozen contract."""
    bodies = _committed_bodies()
    bodies["contracts/prim/schema.json"] += b"\n"
    result = ci_09.run(_scratch_corpus(tmp_path, bodies, _committed_frozen_hash()))
    assert result.findings, (
        "the JSON mirror changed under a frozen primitive and CI-09 stayed green"
    )
    assert all(f.rule_id == "CI-09" for f in result.findings)


def test_unfrozen_glob_with_content_is_a_finding(tmp_path: Path) -> None:
    """Vacuous-safe: a frozen glob with content but no FROZEN hash is still caught."""
    root = tmp_path
    for relative, content in _committed_bodies().items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (root / "registry" / "contracts").mkdir(parents=True, exist_ok=True)
    (root / AUTHORITY).write_text(json.dumps({"contracts": []}), encoding="utf-8")
    built = corpus(
        (
            record(
                wp="WP-3A-00",
                contract={"consumes": [], "produces": [CONTRACT_ID]},
                owns=[{"glob": glob, "mode": "CONTRACT_FROZEN"} for glob in FROZEN_GLOBS],
            ),
        ),
        root=root,
        tracked_files=FROZEN_GLOBS,
    )
    result = ci_09.run(built)
    assert result.findings
    assert "no FROZEN hash" in result.findings[0].reason
