"""CONTRACT_FROZEN enforcement — WP-BOOT-05 acceptance ②.

The sharp edge of the package. `06` §4.3 deleted the optional-field exemption
that a previous revision granted, and the deletion is the point: while a
carve-out existed, "it's only an optional field" was a standing route around
the freeze, and one `@v1` token could name two different schemas.
"""

from __future__ import annotations

import copy

import pytest

from registry.contracts.index import (
    FROZEN,
    build_index,
    freeze_contract,
)
from registry.contracts.violations import ContractViolationError
from tests.boot05.conftest import schema_with, with_optional_field

BASE = schema_with("motor_zero_raw", "urdf_zero_offset")


def _record(store, contract_id: str) -> dict:
    """Return one contract record from the freshly derived index.

    Args:
        store: Contract store to read.
        contract_id: Generation to look up.

    Returns:
        dict: The record for `contract_id`.
    """
    index = build_index(store)
    return next(row for row in index["contracts"] if row["contract_id"] == contract_id)


def test_first_freeze_locks_the_hash(store) -> None:
    """Freezing records the content hash and flips the status."""
    outcome = freeze_contract(store, "CTR-CAL@v1", BASE)
    assert outcome.record.status == FROZEN
    assert outcome.record.canonical_hash is not None
    assert outcome.already_frozen is False
    assert _record(store, "CTR-CAL@v1")["status"] == FROZEN


def test_refreezing_changed_content_is_rejected(store) -> None:
    """A required-field change under the same generation fails."""
    freeze_contract(store, "CTR-CAL@v1", BASE)
    changed = schema_with("motor_zero_raw", "urdf_zero_offset", "sign")

    with pytest.raises(ContractViolationError) as raised:
        freeze_contract(store, "CTR-CAL@v1", changed)
    assert raised.value.violation.rule == "CI-09"
    assert "CTR-CAL@v2" in raised.value.violation.expected


def test_adding_an_optional_field_is_rejected(store) -> None:
    """The exemption that does not exist (acceptance ②, the explicit case).

    An optional field breaks nothing at runtime, which is exactly why it was
    once exempt and exactly why it must not be: the exemption is what makes
    "which schema did I implement against?" unanswerable.
    """
    freeze_contract(store, "CTR-CAL@v1", BASE)
    extended = with_optional_field(BASE, "captured_flag")

    with pytest.raises(ContractViolationError) as raised:
        freeze_contract(store, "CTR-CAL@v1", extended)
    assert raised.value.violation.rule == "CI-09"


def test_removing_a_field_is_rejected(store) -> None:
    """Shrinking the schema is a change like any other."""
    freeze_contract(store, "CTR-CAL@v1", BASE)
    with pytest.raises(ContractViolationError):
        freeze_contract(store, "CTR-CAL@v1", schema_with("motor_zero_raw"))


def test_rejected_refreeze_leaves_the_locked_hash_intact(store) -> None:
    """A refused change must not half-apply to the ledger."""
    original = freeze_contract(store, "CTR-CAL@v1", BASE).record.canonical_hash
    with pytest.raises(ContractViolationError):
        freeze_contract(store, "CTR-CAL@v1", with_optional_field(BASE, "captured_flag"))
    assert _record(store, "CTR-CAL@v1")["canonical_hash"] == original


def test_identical_refreeze_is_accepted(store) -> None:
    """Re-registering the same content is not a change — no over-blocking.

    Without this the checker would fail on any re-run of its own build step,
    and a checker that fails on a no-op gets disabled.
    """
    first = freeze_contract(store, "CTR-CAL@v1", BASE)
    second = freeze_contract(store, "CTR-CAL@v1", copy.deepcopy(BASE))
    assert second.already_frozen is True
    assert second.record.canonical_hash == first.record.canonical_hash


def test_documentation_edit_does_not_break_the_freeze(store) -> None:
    """`06` §4.3 keeps the generation when only prose changed."""
    freeze_contract(store, "CTR-CAL@v1", BASE)
    documented = copy.deepcopy(BASE)
    documented["description"] = "Disk calibration contract."
    documented["properties"]["motor_zero_raw"]["description"] = "Raw encoder count at zero."

    outcome = freeze_contract(store, "CTR-CAL@v1", documented)
    assert outcome.already_frozen is True


def test_freezing_one_contract_leaves_the_others_draft(store) -> None:
    """The lock is per generation, not global."""
    freeze_contract(store, "CTR-CAL@v1", BASE)
    assert _record(store, "CTR-ACT@v1")["status"] == "DRAFT"
    assert _record(store, "CTR-ACT@v1")["canonical_hash"] is None


def test_unrelated_contract_can_still_freeze_afterwards(store) -> None:
    """A frozen contract does not block its neighbours (no over-blocking)."""
    freeze_contract(store, "CTR-CAL@v1", BASE)
    outcome = freeze_contract(store, "CTR-ACT@v1", schema_with("requestedPositionAction"))
    assert outcome.record.status == FROZEN
