"""Acceptance ⑦ — cancelling enumerates un-integrated output and leaves integrated output alone.

This is where the closure and the state store meet: the closure says *which* packages a trigger
invalidates, and the store says which of those still hold work that cancellation can reach.
Integrated work is out of scope for cancellation by `05` §5.2 P-4 — it is undone by a named
revert WP instead, and conflating the two would quietly revert merged work under the name of a
cancel.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from registry.state.closure import descendant_closure, load_graph
from registry.state.model import WorkPackageState
from registry.state.store import StateStore

TRIGGER = "PG-SAFE-001:FAIL_BLOCKING"
EVIDENCE = "sha256:" + "d" * 64

ACTIVE_WP = "WP-A-01"
INTEGRATED_WP = "WP-B-01"
NOT_STARTED_WP = "WP-C-01"
CANCELLED_WP = "WP-D-01"


def _chain_registry(path: Path) -> Path:
    """Write a four-package propagation chain.

    Args:
        path: Destination file.

    Returns:
        (Path): The file written.
    """
    entries = [
        {
            "req": "PLAN-BOOT-01",
            "wp": ACTIVE_WP,
            "stale_on": [TRIGGER],
            "downstream": [INTEGRATED_WP],
            "artifact": [],
        },
        {
            "req": "PLAN-BOOT-02",
            "wp": INTEGRATED_WP,
            "stale_on": [],
            "downstream": [NOT_STARTED_WP],
            "artifact": [],
        },
        {
            "req": "PLAN-BOOT-03",
            "wp": NOT_STARTED_WP,
            "stale_on": [],
            "downstream": [CANCELLED_WP],
            "artifact": [],
        },
        {
            "req": "PLAN-BOOT-04",
            "wp": CANCELLED_WP,
            "stale_on": [],
            "downstream": [],
            "artifact": [],
        },
    ]
    path.write_text(
        yaml.safe_dump({"version": 1, "spine_ref": "test", "entries": entries}),
        encoding="utf-8",
    )
    return path


def _seed_states(store: StateStore) -> None:
    """Put each package of the chain into a different state.

    Args:
        store: Store to populate.
    """
    store.transition(ACTIVE_WP, WorkPackageState.ACTIVE, "spawn", EVIDENCE)
    store.transition(INTEGRATED_WP, WorkPackageState.ACTIVE, "spawn", EVIDENCE)
    store.transition(INTEGRATED_WP, WorkPackageState.INTEGRATED, "merge", EVIDENCE)
    store.transition(CANCELLED_WP, WorkPackageState.ACTIVE, "spawn", EVIDENCE)
    store.transition(CANCELLED_WP, WorkPackageState.CANCELLED, "earlier-cancel", EVIDENCE)


def test_cancellation_enumerates_only_unintegrated_packages(tmp_path: Path) -> None:
    """Acceptance ⑦ — active and unstarted work is enumerated; integrated work is not."""
    graph = load_graph(_chain_registry(tmp_path / "chain.yaml"))
    store = StateStore(tmp_path / "state")
    _seed_states(store)

    closure = descendant_closure(graph, TRIGGER)
    targets = store.cancellable(sorted(closure.wps))

    assert closure.wps == {ACTIVE_WP, INTEGRATED_WP, NOT_STARTED_WP, CANCELLED_WP}
    assert ACTIVE_WP in targets
    assert NOT_STARTED_WP in targets
    assert INTEGRATED_WP not in targets, "integrated output must not be cancelled"
    assert CANCELLED_WP not in targets, "already cancelled work is not cancelled twice"


def test_integrated_package_is_still_marked_stale(tmp_path: Path) -> None:
    """Excluded from cancellation is not the same as excluded from the closure.

    `05` §5.2 keeps stale marking (P-3) separate from cancellation (P-4); an integrated package
    is stamped stale and left in place so a replacement can read what died and why.
    """
    graph = load_graph(_chain_registry(tmp_path / "chain.yaml"))
    store = StateStore(tmp_path / "state")
    _seed_states(store)

    closure = descendant_closure(graph, TRIGGER)
    assert INTEGRATED_WP in closure.wps

    record = store.transition(INTEGRATED_WP, WorkPackageState.STALE, TRIGGER, EVIDENCE)
    assert record.previous_state is WorkPackageState.INTEGRATED
    assert store.state_of(INTEGRATED_WP) is WorkPackageState.STALE
    assert store.cancellable([INTEGRATED_WP]) == [INTEGRATED_WP]


def test_cancellation_records_the_trigger_as_evidence(tmp_path: Path) -> None:
    """Every cancellation carries the trigger that caused it into the log."""
    store = StateStore(tmp_path / "state")
    store.transition(ACTIVE_WP, WorkPackageState.ACTIVE, "spawn", EVIDENCE)
    store.transition(ACTIVE_WP, WorkPackageState.CANCELLED, TRIGGER, EVIDENCE)

    cancellation = store.transitions()[-1]
    assert cancellation.new_state is WorkPackageState.CANCELLED
    assert cancellation.trigger == TRIGGER
    assert cancellation.evidence_hash == EVIDENCE


def test_unknown_packages_default_to_cancellable(tmp_path: Path) -> None:
    """A package with no record has not started, so nothing about it is integrated."""
    store = StateStore(tmp_path / "state")
    assert store.cancellable(["WP-9Z-99"]) == ["WP-9Z-99"]
