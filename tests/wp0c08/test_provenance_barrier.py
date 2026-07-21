"""Manifest hashes — the matrix provenance clears both launch barriers.

Wave 0-C is downstream of WP-ENV-04 and WP-N1-04, so the matrix declares an
`env_hash` and a `normalization_hash` (`06` §2.2): the ceilings are introspected off
a pinned environment, so the artifact records which one. This suite proves the
provenance stamps the currently-issued values and is therefore cleared by both
launch barriers, and that a manifest missing a hash is refused — the barrier bites.
"""

from __future__ import annotations

import pytest

from backend.policy_matrix.provenance import build_provenance_manifest
from registry.env.barrier import check_manifest as check_env
from registry.env.env_hash import read_issued as read_env_hash
from registry.normalization.barrier import check_manifest as check_normalization
from registry.normalization.content_hash import ISSUED_PATH as NORMALIZATION_ISSUED_PATH
from registry.normalization.content_hash import read_issued as read_normalization_hash


def test_provenance_stamps_the_issued_hashes() -> None:
    """The manifest carries WP-0C-08 and the two currently-issued hashes."""
    manifest = build_provenance_manifest({"policies": ["smolvla", "groot"]})
    assert manifest["wp_id"] == "WP-0C-08"
    assert manifest["env_hash"] == read_env_hash()
    assert manifest["normalization_hash"] == read_normalization_hash(NORMALIZATION_ISSUED_PATH)


def test_provenance_clears_both_barriers() -> None:
    """Both launch barriers clear the stamped provenance manifest."""
    manifest = build_provenance_manifest({"policies": ["groot"]})
    env_issued = read_env_hash()
    norm_issued = read_normalization_hash(NORMALIZATION_ISSUED_PATH)
    assert env_issued is not None and norm_issued is not None

    assert not check_env(manifest, env_issued).blocked
    assert not check_normalization(manifest, norm_issued).blocked


def test_missing_hash_is_refused() -> None:
    """A manifest that declares no hash is refused start — the barrier bites."""
    env_issued = read_env_hash()
    norm_issued = read_normalization_hash(NORMALIZATION_ISSUED_PATH)
    assert env_issued is not None and norm_issued is not None

    absent = {"wp_id": "WP-0C-08", "env_hash": None, "normalization_hash": None}
    assert check_env(absent, env_issued).blocked
    assert check_normalization(absent, norm_issued).blocked


def test_superseded_hash_is_refused() -> None:
    """A manifest citing a stale hash is refused start."""
    manifest = build_provenance_manifest({"policies": ["groot"]})
    stale = "sha256:" + "0" * 64
    assert check_env(manifest, stale).blocked
    assert check_normalization(manifest, stale).blocked


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
