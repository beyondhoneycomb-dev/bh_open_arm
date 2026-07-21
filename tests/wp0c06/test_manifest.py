"""The harness manifest declares both hashes and clears both launch barriers.

Wave 0-C is downstream of WP-ENV-04 and WP-N1-04, so a harness artifact declares an
``env_hash`` and a ``normalization_hash`` (`06` §2.2). This mirrors the Wave 0-C
dataset provenance: the manifest clears both barriers when stamped with the issued
values, and a manifest missing a hash is refused start.
"""

from __future__ import annotations

import pytest

from registry.env.barrier import check_manifest as check_env
from registry.env.env_hash import read_issued as read_env_hash
from registry.normalization.barrier import check_manifest as check_normalization
from registry.normalization.content_hash import ISSUED_PATH as NORMALIZATION_ISSUED_PATH
from registry.normalization.content_hash import read_issued as read_normalization_hash
from sim.harness.artifact import WP_ID, build_manifest


def test_manifest_stamps_issued_hashes() -> None:
    """The manifest carries WP-0C-06 and the two currently-issued hashes."""
    manifest = build_manifest()
    assert manifest["wp_id"] == WP_ID
    assert manifest["env_hash"] == read_env_hash()
    assert manifest["normalization_hash"] == read_normalization_hash(NORMALIZATION_ISSUED_PATH)


def test_manifest_clears_both_barriers() -> None:
    """Both launch barriers clear the stamped manifest."""
    manifest = build_manifest()
    env_issued = read_env_hash()
    norm_issued = read_normalization_hash(NORMALIZATION_ISSUED_PATH)
    assert env_issued is not None and norm_issued is not None
    assert not check_env(manifest, env_issued).blocked
    assert not check_normalization(manifest, norm_issued).blocked


def test_missing_hash_is_refused() -> None:
    """A manifest declaring no hash is refused start — the barrier bites."""
    env_issued = read_env_hash()
    norm_issued = read_normalization_hash(NORMALIZATION_ISSUED_PATH)
    assert env_issued is not None and norm_issued is not None
    absent = {"wp_id": WP_ID, "env_hash": None, "normalization_hash": None}
    assert check_env(absent, env_issued).blocked
    assert check_normalization(absent, norm_issued).blocked


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
