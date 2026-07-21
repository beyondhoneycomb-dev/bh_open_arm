"""A schema change without a contract-version bump is rejected (WP-0A-02).

Acceptance ⑧: the frozen schema pins the digest of its own content; a change that
does not bump the contract version leaves that digest stale, and the version guard
rejects it. This models CI-09's freeze rule (06 §4.3) locally until the freeze
registry (WP-BOOT-05) is standing: any content change is a new generation.
"""

from __future__ import annotations

import copy
from typing import Any

import yaml

from contracts.action import check_version_bump, schema_digest, verify_frozen_digest
from contracts.action.schema import CONTRACT_PATH


def _document() -> dict[str, Any]:
    """Return the shipped contract document parsed from YAML."""
    return yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_shipped_digest_matches_content() -> None:
    """The frozen file's pinned digest matches its own content."""
    assert verify_frozen_digest(_document()) == ()


def test_added_channel_moves_the_digest() -> None:
    """Any schema change moves the content digest."""
    original = _document()
    mutated = copy.deepcopy(original)
    mutated["channels"].append({"name": "extra", "role": "observation"})
    assert schema_digest(original) != schema_digest(mutated)


def test_change_without_bump_is_rejected() -> None:
    """A changed schema keeping the same @v1 version is rejected (acceptance ⑧)."""
    previous = _document()
    current = copy.deepcopy(previous)
    current["channels"][0]["dim"] = 24  # changed schema, version left CTR-ACT@v1
    verdict = check_version_bump(previous, current)
    assert not verdict.accepted
    assert "version was not bumped" in verdict.reason


def test_change_with_bump_is_accepted() -> None:
    """A changed schema that bumps the version to @v2 is accepted."""
    previous = _document()
    current = copy.deepcopy(previous)
    current["channels"][0]["dim"] = 24
    current["contract"] = "CTR-ACT@v2"
    assert check_version_bump(previous, current).accepted


def test_no_change_is_accepted() -> None:
    """An identical revision is a no-op, not a violation."""
    document = _document()
    assert check_version_bump(document, copy.deepcopy(document)).accepted
