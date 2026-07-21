"""WP-ENV-04 acceptance ⑦ — a manifest lacking (or misciting) env_hash is refused start."""

from __future__ import annotations

from registry.env.barrier import REASON_ABSENT, REASON_MISMATCH, check_manifest

ISSUED = "sha256:" + "a" * 64


def test_manifest_without_env_hash_is_blocked() -> None:
    verdict = check_manifest({"wp_id": "WP-2A-01"}, ISSUED)
    assert verdict.blocked
    assert verdict.reason == REASON_ABSENT


def test_manifest_with_superseded_env_hash_is_blocked() -> None:
    verdict = check_manifest({"wp_id": "WP-2A-01", "env_hash": "sha256:" + "b" * 64}, ISSUED)
    assert verdict.blocked
    assert verdict.reason == REASON_MISMATCH


def test_manifest_with_current_env_hash_clears() -> None:
    verdict = check_manifest({"wp_id": "WP-2A-01", "env_hash": ISSUED}, ISSUED)
    assert not verdict.blocked
