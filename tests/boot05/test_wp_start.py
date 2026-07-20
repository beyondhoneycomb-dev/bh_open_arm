"""Consume-before-freeze rejection at start — WP-BOOT-05 acceptance ⑨.

`CR-2` blocks a work package whose `consumes` axis names a contract nobody has
frozen. A consumer that starts against a draft has read a schema its producer
may still change, and once it has, no later check can establish which version
it implemented against — the freeze exists to make that question answerable.
"""

from __future__ import annotations

import json

from registry.contracts.index import (
    check_wp_start,
    freeze_contract,
    retire_contract,
    write_index,
)
from tests.boot05.conftest import rewrite_registry, schema_with

BASE = schema_with("robot_id", "joints")
BUMPED = schema_with("robot_id", "joints", "gripper_rad")


def test_start_is_blocked_while_the_contract_is_draft(store) -> None:
    """The unfrozen-consume case (acceptance ⑨)."""
    violations = check_wp_start(store, "WP-0C-01")
    assert [violation.rule for violation in violations] == ["CR-2"]
    assert "CTR-PLUG@v1" in violations[0].actual


def test_start_is_allowed_once_the_contract_is_frozen(store) -> None:
    """The same work package proceeds after the freeze (no over-blocking)."""
    freeze_contract(store, "CTR-PLUG@v1", BASE)
    assert check_wp_start(store, "WP-0C-01") == []


def test_every_unfrozen_contract_is_reported(store) -> None:
    """A consumer of two drafts gets both, not the first one only."""
    violations = check_wp_start(store, "WP-1-03")
    assert {violation.location.split()[-1] for violation in violations} == {
        "CTR-ACT@v1",
        "CTR-CAL@v1",
    }


def test_partial_freeze_still_blocks(store) -> None:
    """Freezing one of two consumed contracts is not enough."""
    freeze_contract(store, "CTR-ACT@v1", BASE)
    violations = check_wp_start(store, "WP-1-03")
    assert [violation.location.split()[-1] for violation in violations] == ["CTR-CAL@v1"]


def test_work_package_consuming_nothing_may_start(store) -> None:
    """No consumed contracts means no contract-side reason to block."""
    assert check_wp_start(store, "WP-0A-03") == []


def test_start_is_allowed_against_a_superseded_generation(store) -> None:
    """`06` §4.3 step 3 keeps the old path alive until replacements land."""
    freeze_contract(store, "CTR-PLUG@v1", BASE)
    freeze_contract(store, "CTR-PLUG@v2", BUMPED)
    assert check_wp_start(store, "WP-0C-01") == []


def test_start_is_blocked_against_a_retired_generation(store) -> None:
    """`06` §4.3 step 4 — consuming a retired contract fails the build."""
    freeze_contract(store, "CTR-PLUG@v1", BASE)
    freeze_contract(store, "CTR-PLUG@v2", BUMPED)
    retire_contract(store, "CTR-PLUG@v1")

    violations = check_wp_start(store, "WP-0C-01")
    assert [violation.rule for violation in violations] == ["CR-2"]
    assert "RETIRED" in violations[0].actual


def test_start_check_ignores_a_hand_edited_index(store) -> None:
    """The gate derives its state, so forging the index does not open it.

    A check that trusted the persisted index would be defeated by the same edit
    the integrity check exists to catch, and the two would have to agree for
    either to mean anything.
    """
    write_index(store)
    index = json.loads(store.index_path.read_text(encoding="utf-8"))
    for row in index["contracts"]:
        if row["contract_id"] == "CTR-PLUG@v1":
            row["status"] = "FROZEN"
            row["canonical_hash"] = "sha256:" + "0" * 64
    store.index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

    assert [violation.rule for violation in check_wp_start(store, "WP-0C-01")] == ["CR-2"]


def test_consuming_an_unregistered_contract_is_blocked(store) -> None:
    """A `consumes` entry with no index record cannot be started against."""
    rewrite_registry(
        store,
        [{"req": "FR-SYS-014", "wp": "WP-0C-01", "contract": {"consumes": ["CTR-PLUG@v7"]}}],
    )
    violations = check_wp_start(store, "WP-0C-01")
    assert [violation.rule for violation in violations] == ["CR-2"]
    assert "not registered" in violations[0].actual


def test_freezing_one_contract_does_not_unblock_another_work_package(store) -> None:
    """The gate is per work package, per consumed contract."""
    freeze_contract(store, "CTR-PLUG@v1", BASE)
    assert check_wp_start(store, "WP-0C-01") == []
    assert check_wp_start(store, "WP-1-03") != []
