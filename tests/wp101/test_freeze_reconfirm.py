"""Acceptance (6): CTR-PLUG@v1 is registered, and the freeze lock rejects a bump-less change.

Light lane — reads the committed freeze authority and drives CI-09 over scratch
corpora, no LeRobot import.

Two facts, kept separate on purpose:

- CTR-PLUG@v1 is registered in the freeze authority, owned by WP-0A-02 (01 §6.2).
  WP-1-01 re-confirms this on the hardware axis; it does NOT freeze the contract —
  Wave 0-C consumes it, so a Wave-1 freeze would make that a CR-2 violation.
- The CI-09 drift lock fires on a one-byte change to a CONTRACT_FROZEN glob with no
  `@v(n+1)` bump. This is proven the same way the committed CTR-ERR / CTR-UNIT locks
  are (tests/wpops06, tests/boot05): a scratch corpus that freezes CTR-PLUG@v1 at a
  file's hash, then mutates one byte, must make CI-09 fire. It is the mechanism that
  arms the moment WP-0A-02 declares the CONTRACT_FROZEN glob (its deliverable).
"""

from __future__ import annotations

import json
from pathlib import Path

from contracts.plugin_api import freeze
from registry.checks import ci_09
from registry.checks.corpus import Corpus
from registry.checks.fixtures import corpus, record

REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN_GLOB = "contracts/plugin/ctr_plug_spec.yaml"
AUTHORITY = "registry/contracts/contract_index.json"
CONTRACT_ID = "CTR-PLUG@v1"


def test_ctr_plug_is_registered_and_owned_by_wp_0a02() -> None:
    """CTR-PLUG@v1 is present in the freeze authority, owned by WP-0A-02 (01 §6.2)."""
    state = freeze.registration(REPO_ROOT)
    assert state.present, "CTR-PLUG@v1 must be registered in the freeze authority"
    assert state.owner_wp == freeze.OWNER_WP == "WP-0A-02"


def test_real_repo_ci09_is_green() -> None:
    """WP-1-01's files introduce no frozen-contract drift on the real tree."""
    result = ci_09.run(Corpus(REPO_ROOT))
    assert not result.findings


def _scratch_corpus(root: Path, spec_bytes: bytes, frozen_hash: str) -> Corpus:
    """Build a corpus that freezes CTR-PLUG@v1 at a given hash over a scratch tree.

    Args:
        root: Scratch repository root.
        spec_bytes: Bytes to write at the frozen glob path.
        frozen_hash: The canonical_hash the authority records as FROZEN.

    Returns:
        (Corpus) A corpus CI-09 can run without touching the real tree.
    """
    (root / "contracts" / "plugin").mkdir(parents=True, exist_ok=True)
    (root / FROZEN_GLOB).write_bytes(spec_bytes)
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
                wp=freeze.OWNER_WP,
                contract={"consumes": [], "produces": [CONTRACT_ID]},
                owns=[{"glob": FROZEN_GLOB, "mode": "CONTRACT_FROZEN"}],
            ),
        ),
        root=root,
        tracked_files=(FROZEN_GLOB,),
    )


def test_matching_content_is_green(tmp_path: Path) -> None:
    """With the frozen bytes and their hash, CI-09 accepts CTR-PLUG@v1."""
    spec = b"frozen: CTR-PLUG@v1\n"
    # content_hash reads the file, so write it before hashing.
    (tmp_path / "contracts" / "plugin").mkdir(parents=True, exist_ok=True)
    (tmp_path / FROZEN_GLOB).write_bytes(spec)
    frozen_hash = ci_09.content_hash((FROZEN_GLOB,), tmp_path)
    result = ci_09.run(_scratch_corpus(tmp_path, spec, frozen_hash))
    assert not result.findings
    assert result.sites == 1


def test_one_byte_drift_fires(tmp_path: Path) -> None:
    """Acceptance (6): a byte changes under a frozen CTR-PLUG@v1 and CI-09 must fire."""
    spec = b"frozen: CTR-PLUG@v1\n"
    (tmp_path / "contracts" / "plugin").mkdir(parents=True, exist_ok=True)
    (tmp_path / FROZEN_GLOB).write_bytes(spec)
    frozen_hash = ci_09.content_hash((FROZEN_GLOB,), tmp_path)
    result = ci_09.run(_scratch_corpus(tmp_path, spec + b" ", frozen_hash))
    assert result.findings, "a byte changed under a frozen contract and CI-09 stayed green"
    assert all(f.rule_id == "CI-09" for f in result.findings)
    assert "differs from its registered hash" in result.findings[0].reason
