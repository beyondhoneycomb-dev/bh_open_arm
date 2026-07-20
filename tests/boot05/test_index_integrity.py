"""Index integrity and bypass closure — WP-BOOT-05 acceptance ⑦ and ⑧.

A lock whose bookkeeping can be hand-edited is not a lock. These tests do the
edit and require the static check to catch it — and equally require it to stay
quiet on an untouched tree, because a check that fires on clean input gets
switched off and then catches nothing at all.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import yaml

from registry.contracts import ledger
from registry.contracts.index import (
    build_index,
    freeze_contract,
    verify_index,
    write_index,
)
from registry.contracts.violations import ContractViolationError
from tests.boot05.conftest import PLUG_CONSUMERS, rewrite_registry, schema_with

BASE = schema_with("robot_id", "joints")


def _load(store) -> dict[str, Any]:
    """Read the persisted index.

    Args:
        store: Contract store to read.

    Returns:
        dict[str, Any]: The parsed index document.
    """
    return json.loads(store.index_path.read_text(encoding="utf-8"))


def _save(store, index: dict[str, Any]) -> None:
    """Write an index document directly, as a hand edit would.

    Args:
        store: Contract store to write.
        index: Document to persist.
    """
    store.index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")


def _record(index: dict[str, Any], contract_id: str) -> dict[str, Any]:
    """Return one record from an index document.

    Args:
        index: Index document.
        contract_id: Generation to look up.

    Returns:
        dict[str, Any]: The matching record.
    """
    return next(row for row in index["contracts"] if row["contract_id"] == contract_id)


def test_freshly_built_index_verifies(store) -> None:
    """A clean tree produces no findings (no over-blocking)."""
    write_index(store)
    assert verify_index(store) == []


def test_index_verifies_after_a_freeze(store) -> None:
    """Freezing keeps the persisted index consistent with its sources."""
    freeze_contract(store, "CTR-PLUG@v1", BASE)
    assert verify_index(store) == []


def test_index_verifies_after_a_bump(store) -> None:
    """A bump rewrites the index consistently, triggers included."""
    freeze_contract(store, "CTR-PLUG@v1", BASE)
    freeze_contract(store, "CTR-PLUG@v2", schema_with("robot_id", "joints", "gripper_rad"))
    assert verify_index(store) == []


def test_missing_index_is_reported(store) -> None:
    """A deleted index is a finding, not a silent pass."""
    freeze_contract(store, "CTR-PLUG@v1", BASE)
    store.index_path.unlink()
    violations = verify_index(store)
    assert [violation.rule for violation in violations] == ["CI-09"]


def test_hand_edited_hash_is_rejected(store) -> None:
    """The direct route around the freeze: rewrite the recorded hash."""
    freeze_contract(store, "CTR-PLUG@v1", BASE)
    index = _load(store)
    _record(index, "CTR-PLUG@v1")["canonical_hash"] = "sha256:" + "0" * 64
    _save(store, index)

    violations = verify_index(store)
    assert any(
        violation.rule == "CI-09" and violation.location.endswith("/canonical_hash")
        for violation in violations
    )


def test_hand_edited_status_is_rejected(store) -> None:
    """Promoting a draft to frozen by editing text does not make it frozen."""
    write_index(store)
    index = _load(store)
    _record(index, "CTR-PLUG@v1")["status"] = "FROZEN"
    _save(store, index)

    violations = verify_index(store)
    assert any(violation.location.endswith("/status") for violation in violations)


def test_hand_edited_owner_is_rejected(store) -> None:
    """Ownership comes from `01` §6.2 and cannot be reassigned in the index."""
    write_index(store)
    index = _load(store)
    _record(index, "CTR-PLUG@v1")["owner_wp"] = "WP-9Z-99"
    _save(store, index)

    violations = verify_index(store)
    assert any(violation.rule == "CI-03" for violation in violations)


def test_invented_contract_in_the_index_is_rejected(store) -> None:
    """A record with no source is caught as a namespace breach."""
    write_index(store)
    index = _load(store)
    index["contracts"].append(
        {
            "contract_id": "CTR-SCHEDULERMAILBOX@v1",
            "version": 1,
            "canonical_hash": "sha256:" + "1" * 64,
            "status": "FROZEN",
            "owner_wp": "WP-0A-01",
            "consumer_wps": [],
        }
    )
    _save(store, index)

    violations = verify_index(store)
    assert any(violation.rule == "CI-03c" for violation in violations)


def test_deleted_record_is_rejected(store) -> None:
    """Removing a contract from the index does not remove its obligation."""
    write_index(store)
    index = _load(store)
    index["contracts"] = [row for row in index["contracts"] if row["contract_id"] != "CTR-PLUG@v1"]
    _save(store, index)

    violations = verify_index(store)
    assert any("CTR-PLUG@v1" in violation.location for violation in violations)


def test_forged_trigger_list_is_rejected(store) -> None:
    """Re-verification obligations cannot be deleted from the index."""
    freeze_contract(store, "CTR-PLUG@v1", BASE)
    freeze_contract(store, "CTR-PLUG@v2", schema_with("robot_id", "joints", "gripper_rad"))
    index = _load(store)
    index["reverification_triggers"] = []
    _save(store, index)

    violations = verify_index(store)
    assert any("reverification_triggers" in violation.location for violation in violations)


def test_forged_ledger_head_is_rejected(store) -> None:
    """The index cannot claim a ledger state the ledger does not have."""
    freeze_contract(store, "CTR-PLUG@v1", BASE)
    index = _load(store)
    index["ledger_head"] = "0" * 64
    _save(store, index)

    assert any(violation.location.endswith("#ledger_head") for violation in verify_index(store))


def test_ledger_entry_edited_in_place_is_detected(store) -> None:
    """Rewriting a recorded freeze breaks the digest chain."""
    freeze_contract(store, "CTR-PLUG@v1", BASE)
    document = yaml.safe_load(store.ledger_path.read_text(encoding="utf-8"))
    document["events"][0]["canonical_hash"] = "sha256:" + "2" * 64
    store.ledger_path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    violations = verify_index(store)
    assert any("edited in place" in violation.actual for violation in violations)


def test_ledger_event_deleted_is_detected(store) -> None:
    """Dropping a freeze event breaks the sequence and the linkage."""
    freeze_contract(store, "CTR-PLUG@v1", BASE)
    freeze_contract(store, "CTR-PLUG@v2", schema_with("robot_id", "joints", "gripper_rad"))
    document = yaml.safe_load(store.ledger_path.read_text(encoding="utf-8"))
    del document["events"][0]
    store.ledger_path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    assert verify_index(store) != []


def test_build_refuses_to_run_on_a_tampered_ledger(store) -> None:
    """A broken chain must not be laundered into a freshly built index."""
    freeze_contract(store, "CTR-PLUG@v1", BASE)
    document = yaml.safe_load(store.ledger_path.read_text(encoding="utf-8"))
    document["events"][0]["digest"] = "9" * 64
    store.ledger_path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    with pytest.raises(ContractViolationError):
        build_index(store)


def test_rebuilding_repairs_a_hand_edited_index(store) -> None:
    """The index is derived, so regeneration is the remedy for an edit."""
    freeze_contract(store, "CTR-PLUG@v1", BASE)
    index = _load(store)
    _record(index, "CTR-PLUG@v1")["canonical_hash"] = "sha256:" + "0" * 64
    _save(store, index)
    assert verify_index(store) != []

    write_index(store)
    assert verify_index(store) == []


def test_consumer_axis_mirrors_the_registry(store) -> None:
    """Acceptance ⑦ — consumers come from the registry, not a second list."""
    index = write_index(store)
    assert tuple(_record(index, "CTR-PLUG@v1")["consumer_wps"]) == PLUG_CONSUMERS


def test_doctored_consumer_list_is_rejected(store) -> None:
    """An index that disagrees with the `consumes` axis is a second truth."""
    write_index(store)
    index = _load(store)
    _record(index, "CTR-PLUG@v1")["consumer_wps"] = ["WP-0C-01"]
    _save(store, index)

    violations = verify_index(store)
    assert any(
        violation.rule == "CR-5" and violation.location.endswith("/consumer_wps")
        for violation in violations
    )


def test_added_consumer_is_rejected(store) -> None:
    """Inventing a consumer is caught as readily as deleting one."""
    write_index(store)
    index = _load(store)
    _record(index, "CTR-PLUG@v1")["consumer_wps"] = [*PLUG_CONSUMERS, "WP-4A-07"]
    _save(store, index)

    assert any(violation.rule == "CR-5" for violation in verify_index(store))


def test_registry_change_makes_a_stale_index_fail(store) -> None:
    """A consumer added to the registry invalidates the persisted index."""
    write_index(store)
    assert verify_index(store) == []

    rewrite_registry(
        store,
        [{"req": "FR-SYS-014", "wp": "WP-5-11", "contract": {"consumes": ["CTR-PLUG@v1"]}}],
    )
    assert any(violation.rule == "CR-5" for violation in verify_index(store))


def test_deferred_records_are_not_consumers(store) -> None:
    """A `DEFERRED` requirement has no work package that could start."""
    index = write_index(store)
    assert _record(index, "CTR-WS@v1")["consumer_wps"] == ["WP-G-01"]


def test_ledger_is_append_only_across_operations(store) -> None:
    """Every transition adds an event; none rewrites one."""
    freeze_contract(store, "CTR-PLUG@v1", BASE)
    first = ledger.read_ledger(store.ledger_path)
    freeze_contract(store, "CTR-PLUG@v2", schema_with("robot_id", "joints", "gripper_rad"))
    second = ledger.read_ledger(store.ledger_path)

    assert second[: len(first)] == first
    assert [event.kind for event in second] == ["FREEZE", "SUPERSEDE", "FREEZE"]
    assert ledger.verify_chain(second) == []
