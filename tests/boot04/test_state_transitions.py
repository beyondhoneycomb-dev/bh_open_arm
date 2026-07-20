"""Acceptance ① — the five-state transition table, with illegal transitions rejected.

Acceptance ⑧ — the transition log's five fields.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from registry.state.model import (
    CANCELLABLE_STATES,
    KOREAN_LABEL,
    LEGAL_TRANSITIONS,
    IllegalTransitionError,
    WorkPackageState,
    is_legal,
)
from registry.state.store import StateStore, StateStoreError

EVIDENCE = "sha256:" + "a" * 64
TRIGGER = "PG-SAFE-001:FAIL_BLOCKING"

# Every transition the plan forbids, with the reason it is forbidden.
ILLEGAL_CASES = [
    # `05` §5.2 P-4: merged work is undone by a named revert WP, not by cancellation.
    (WorkPackageState.INTEGRATED, WorkPackageState.CANCELLED),
    # An integrated package re-opens only via a gate flip marking it stale first.
    (WorkPackageState.INTEGRATED, WorkPackageState.ACTIVE),
    # `05` §5.2 P-6: a cancelled package is replaced by a newly named WP, never resurrected.
    (WorkPackageState.CANCELLED, WorkPackageState.ACTIVE),
    (WorkPackageState.CANCELLED, WorkPackageState.INTEGRATED),
    (WorkPackageState.CANCELLED, WorkPackageState.STALE),
    # No path back to unstarted, and no skipping straight to integrated.
    (WorkPackageState.ACTIVE, WorkPackageState.NOT_STARTED),
    (WorkPackageState.NOT_STARTED, WorkPackageState.INTEGRATED),
    (WorkPackageState.NOT_STARTED, WorkPackageState.STALE),
    (WorkPackageState.STALE, WorkPackageState.INTEGRATED),
]


def test_exactly_five_states() -> None:
    assert len(list(WorkPackageState)) == 5
    assert set(KOREAN_LABEL) == set(WorkPackageState)


def test_transition_table_is_closed() -> None:
    """Every ordered pair is decided: legal or not. Nothing is left undefined."""
    pairs = list(itertools.product(WorkPackageState, WorkPackageState))
    assert len(pairs) == 25
    for previous, new in pairs:
        assert is_legal(previous, new) is ((previous, new) in LEGAL_TRANSITIONS)


def test_no_self_transitions() -> None:
    for state in WorkPackageState:
        assert not is_legal(state, state)


@pytest.mark.parametrize(("previous", "new"), sorted(LEGAL_TRANSITIONS))
def test_pass_fixture_legal_transition_commits(
    tmp_path: Path, previous: WorkPackageState, new: WorkPackageState
) -> None:
    """Pass fixture: each legal transition is accepted and recorded."""
    store = StateStore(tmp_path)
    _force_state(store, "WP-BOOT-04", previous)
    record = store.transition("WP-BOOT-04", new, TRIGGER, EVIDENCE)
    assert record.previous_state is previous
    assert record.new_state is new
    assert store.state_of("WP-BOOT-04") is new


@pytest.mark.parametrize(("previous", "new"), ILLEGAL_CASES)
def test_violation_fixture_illegal_transition_rejected(
    tmp_path: Path, previous: WorkPackageState, new: WorkPackageState
) -> None:
    """Violation fixture: an illegal transition is rejected and does not mutate the store."""
    store = StateStore(tmp_path)
    _force_state(store, "WP-BOOT-04", previous)
    log_before = len(store.transitions())

    with pytest.raises(IllegalTransitionError):
        store.transition("WP-BOOT-04", new, TRIGGER, EVIDENCE)

    assert store.state_of("WP-BOOT-04") is previous
    assert len(store.transitions()) == log_before


def test_unknown_package_starts_not_started(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    assert store.state_of("WP-9Z-99") is WorkPackageState.NOT_STARTED


def test_transition_log_has_exactly_five_fields(tmp_path: Path) -> None:
    """Acceptance ⑧ — {wp, previous_state, new_state, trigger, evidence_hash}, no more."""
    store = StateStore(tmp_path)
    store.transition("WP-BOOT-04", WorkPackageState.ACTIVE, TRIGGER, EVIDENCE)
    store.transition("WP-BOOT-04", WorkPackageState.INTEGRATED, "CG-BOOT-04a:PASS", EVIDENCE)

    records = store.transitions()
    assert len(records) == 2
    for record in records:
        assert set(record.to_json()) == {
            "wp",
            "previous_state",
            "new_state",
            "trigger",
            "evidence_hash",
        }

    first = records[0].to_json()
    assert first["wp"] == "WP-BOOT-04"
    assert first["previous_state"] == "not_started"
    assert first["new_state"] == "active"
    assert first["trigger"] == TRIGGER
    assert first["evidence_hash"] == EVIDENCE


def test_violation_fixture_unevidenced_transition_rejected(tmp_path: Path) -> None:
    """Violation fixture: a transition with no evidence hash or no trigger is refused."""
    store = StateStore(tmp_path)
    with pytest.raises(StateStoreError):
        store.transition("WP-BOOT-04", WorkPackageState.ACTIVE, TRIGGER, "")
    with pytest.raises(StateStoreError):
        store.transition("WP-BOOT-04", WorkPackageState.ACTIVE, "", EVIDENCE)
    assert store.state_of("WP-BOOT-04") is WorkPackageState.NOT_STARTED


def test_cancellable_states_exclude_integrated() -> None:
    assert WorkPackageState.INTEGRATED not in CANCELLABLE_STATES
    assert WorkPackageState.CANCELLED not in CANCELLABLE_STATES
    assert WorkPackageState.ACTIVE in CANCELLABLE_STATES


def _force_state(store: StateStore, wp: str, target: WorkPackageState) -> None:
    """Drive a package to a state using only legal transitions.

    Args:
        store: Store to mutate.
        wp: Work package id.
        target: State to reach.
    """
    paths = {
        WorkPackageState.NOT_STARTED: [],
        WorkPackageState.ACTIVE: [WorkPackageState.ACTIVE],
        WorkPackageState.INTEGRATED: [WorkPackageState.ACTIVE, WorkPackageState.INTEGRATED],
        WorkPackageState.STALE: [WorkPackageState.ACTIVE, WorkPackageState.STALE],
        WorkPackageState.CANCELLED: [WorkPackageState.ACTIVE, WorkPackageState.CANCELLED],
    }
    for step in paths[target]:
        store.transition(wp, step, "setup", EVIDENCE)
