"""`@v(n+1)` issuing and re-verification triggers — WP-BOOT-05 acceptance ③.

What the freeze forbids is changing a contract silently, not versioning it. If
a bump were also blocked there would be no legal way to change a contract at
all, and the lock would be routed around rather than obeyed — so these tests
carry as much weight as the rejection tests.
"""

from __future__ import annotations

import pytest

from registry.contracts.index import (
    FROZEN,
    RETIRED,
    SUPERSEDED,
    build_index,
    freeze_contract,
    retire_contract,
)
from registry.contracts.violations import ContractViolationError
from tests.boot05.conftest import (
    PLUG_CONSUMERS,
    rewrite_registry,
    schema_with,
    with_optional_field,
)

V1 = schema_with("robot_id", "joints")
V2 = with_optional_field(V1, "gripper_rad")


def _status(store, contract_id: str) -> str:
    """Return the recorded status of one generation.

    Args:
        store: Contract store to read.
        contract_id: Generation to look up.

    Returns:
        str: The record's status.
    """
    index = build_index(store)
    return next(row["status"] for row in index["contracts"] if row["contract_id"] == contract_id)


def test_bump_to_next_generation_is_accepted(store) -> None:
    """The change that was refused under `@v1` succeeds as `@v2`."""
    freeze_contract(store, "CTR-PLUG@v1", V1)
    with pytest.raises(ContractViolationError):
        freeze_contract(store, "CTR-PLUG@v1", V2)

    outcome = freeze_contract(store, "CTR-PLUG@v2", V2)
    assert outcome.record.status == FROZEN
    assert outcome.superseded == "CTR-PLUG@v1"


def test_bump_supersedes_the_previous_generation(store) -> None:
    """`06` §4.3 step 1 keeps `@v1` rather than deleting it."""
    freeze_contract(store, "CTR-PLUG@v1", V1)
    freeze_contract(store, "CTR-PLUG@v2", V2)
    assert _status(store, "CTR-PLUG@v1") == SUPERSEDED
    assert _status(store, "CTR-PLUG@v2") == FROZEN


def test_bump_emits_a_trigger_for_every_consumer(store) -> None:
    """Every consuming work package is enumerated, not a sample."""
    freeze_contract(store, "CTR-PLUG@v1", V1)
    outcome = freeze_contract(store, "CTR-PLUG@v2", V2)

    assert tuple(trigger.consumer_wp for trigger in outcome.triggers) == PLUG_CONSUMERS
    for trigger in outcome.triggers:
        assert trigger.contract_id == "CTR-PLUG@v1"
        assert trigger.superseded_by == "CTR-PLUG@v2"
        assert trigger.stale_on == "CTR-PLUG:MAJOR_BUMP"
        assert trigger.required_replacement_wp == f"{trigger.consumer_wp}M2"


def test_triggers_are_persisted_in_the_index(store) -> None:
    """The obligation survives the process that created it."""
    freeze_contract(store, "CTR-PLUG@v1", V1)
    freeze_contract(store, "CTR-PLUG@v2", V2)

    triggers = build_index(store)["reverification_triggers"]
    assert [row["consumer_wp"] for row in triggers] == list(PLUG_CONSUMERS)


def test_initial_freeze_emits_no_triggers(store) -> None:
    """Nothing is stale when nothing was replaced (no over-triggering)."""
    outcome = freeze_contract(store, "CTR-PLUG@v1", V1)
    assert outcome.triggers == ()
    assert build_index(store)["reverification_triggers"] == []


def test_bump_of_a_contract_without_consumers_emits_no_triggers(store) -> None:
    """Trigger fan-out follows the registry, so an unconsumed bump is quiet."""
    freeze_contract(store, "CTR-REC@v1", V1)
    outcome = freeze_contract(store, "CTR-REC@v2", V2)
    assert outcome.superseded == "CTR-REC@v1"
    assert outcome.triggers == ()


def test_bump_without_a_frozen_predecessor_is_rejected(store) -> None:
    """`@v2` cannot be issued against a generation nobody froze."""
    with pytest.raises(ContractViolationError) as raised:
        freeze_contract(store, "CTR-PLUG@v2", V2)
    assert raised.value.violation.rule == "CR-3"


def test_skipping_a_generation_is_rejected(store) -> None:
    """Issuing `@v3` over a frozen `@v1` would strand `@v2`'s consumers."""
    freeze_contract(store, "CTR-PLUG@v1", V1)
    with pytest.raises(ContractViolationError) as raised:
        freeze_contract(store, "CTR-PLUG@v3", V2)
    assert raised.value.violation.rule == "CR-3"


def test_superseded_generation_cannot_be_rewritten(store) -> None:
    """A replaced generation is still frozen against edits."""
    freeze_contract(store, "CTR-PLUG@v1", V1)
    freeze_contract(store, "CTR-PLUG@v2", V2)
    with pytest.raises(ContractViolationError) as raised:
        freeze_contract(store, "CTR-PLUG@v1", schema_with("robot_id"))
    assert raised.value.violation.rule == "CI-09"


def test_second_bump_chains_from_the_current_generation(store) -> None:
    """`@v3` is lawful once `@v2` is the frozen head.

    No trigger is emitted here, and that is the registry speaking rather than a
    gap: nothing in it consumes `@v2` yet, so nothing depends on it. Triggers
    are only ever as complete as the `consumes` axis, which is why they are
    derived from it instead of carried forward from the previous generation.
    """
    freeze_contract(store, "CTR-PLUG@v1", V1)
    freeze_contract(store, "CTR-PLUG@v2", V2)
    outcome = freeze_contract(store, "CTR-PLUG@v3", with_optional_field(V2, "torque_limit"))

    assert outcome.superseded == "CTR-PLUG@v2"
    assert outcome.triggers == ()


def test_triggers_track_consumers_migrated_after_the_bump(store) -> None:
    """A consumer moved onto `@v2` is notified when `@v2` is superseded."""
    freeze_contract(store, "CTR-PLUG@v1", V1)
    freeze_contract(store, "CTR-PLUG@v2", V2)
    rewrite_registry(
        store,
        [{"req": "FR-SYS-014", "wp": "WP-0C-01", "contract": {"consumes": ["CTR-PLUG@v2"]}}],
    )

    outcome = freeze_contract(store, "CTR-PLUG@v3", with_optional_field(V2, "torque_limit"))
    assert [trigger.consumer_wp for trigger in outcome.triggers] == ["WP-0C-01"]
    assert outcome.triggers[0].required_replacement_wp == "WP-0C-01M3"


def test_retiring_a_superseded_generation_closes_the_window(store) -> None:
    """`06` §4.3 step 4 — the old path dies once replacements land."""
    freeze_contract(store, "CTR-PLUG@v1", V1)
    freeze_contract(store, "CTR-PLUG@v2", V2)
    assert retire_contract(store, "CTR-PLUG@v1").status == RETIRED
    assert _status(store, "CTR-PLUG@v1") == RETIRED


def test_retiring_the_current_generation_is_rejected(store) -> None:
    """Retiring the live generation would leave consumers with no successor."""
    freeze_contract(store, "CTR-PLUG@v1", V1)
    with pytest.raises(ContractViolationError) as raised:
        retire_contract(store, "CTR-PLUG@v1")
    assert raised.value.violation.rule == "CR-3"
