"""Manifest hashes — the dataset provenance clears both launch barriers.

Wave 0-C is downstream of WP-ENV-04 and WP-N1-04, so its artifacts declare an
``env_hash`` and a ``normalization_hash`` (`06` §2.2). This suite proves the
provenance manifest stamps the currently-issued values and is therefore *cleared*
by both launch barriers, and that a manifest missing a hash is *refused* — the
barrier is real, not decorative.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.learning.provenance import build_provenance_manifest
from backend.learning.synthetic_dataset import SyntheticDatasetSpec, build_synthetic_dataset
from registry.env.barrier import check_manifest as check_env
from registry.env.env_hash import read_issued as read_env_hash
from registry.normalization.barrier import check_manifest as check_normalization
from registry.normalization.content_hash import ISSUED_PATH as NORMALIZATION_ISSUED_PATH
from registry.normalization.content_hash import read_issued as read_normalization_hash


def test_provenance_stamps_the_issued_hashes() -> None:
    """The manifest carries WP-0C-07 and the two currently-issued hashes."""
    manifest = build_provenance_manifest({"repo_id": "synthetic/x"})
    assert manifest["wp_id"] == "WP-0C-07"
    assert manifest["env_hash"] == read_env_hash()
    assert manifest["normalization_hash"] == read_normalization_hash(NORMALIZATION_ISSUED_PATH)


def test_provenance_clears_both_barriers() -> None:
    """Both launch barriers clear the stamped provenance manifest."""
    manifest = build_provenance_manifest({"repo_id": "synthetic/x"})
    env_issued = read_env_hash()
    norm_issued = read_normalization_hash(NORMALIZATION_ISSUED_PATH)
    assert env_issued is not None and norm_issued is not None

    env_verdict = check_env(manifest, env_issued)
    norm_verdict = check_normalization(manifest, norm_issued)
    assert not env_verdict.blocked, env_verdict.as_line()
    assert not norm_verdict.blocked, norm_verdict.as_line()


def test_built_dataset_carries_clearing_provenance(tmp_path: Path) -> None:
    """A freshly built dataset's provenance clears both barriers."""
    result = build_synthetic_dataset(SyntheticDatasetSpec(), tmp_path / "ds")
    env_issued = read_env_hash()
    norm_issued = read_normalization_hash(NORMALIZATION_ISSUED_PATH)
    assert not check_env(result.provenance, env_issued).blocked
    assert not check_normalization(result.provenance, norm_issued).blocked


def test_missing_hash_is_refused() -> None:
    """A manifest that declares no hash is refused start — the barrier bites."""
    env_issued = read_env_hash()
    norm_issued = read_normalization_hash(NORMALIZATION_ISSUED_PATH)
    assert env_issued is not None and norm_issued is not None

    absent = {"wp_id": "WP-0C-07", "env_hash": None, "normalization_hash": None}
    assert check_env(absent, env_issued).blocked
    assert check_normalization(absent, norm_issued).blocked


def test_superseded_hash_is_refused() -> None:
    """A manifest citing a stale hash is refused start."""
    manifest = build_provenance_manifest({"repo_id": "synthetic/x"})
    stale = "sha256:" + "0" * 64
    assert check_env(manifest, stale).blocked
    assert check_normalization(manifest, stale).blocked


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
