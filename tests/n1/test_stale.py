"""Acceptance ③ — a one-row ledger change bumps the hash and stales its descendants.

Two halves meet here. The content side: a single changed ledger row moves the
issued hash. The propagation side: that bump, injected as `normalization_hash:CHANGED`,
flows through the existing transitive-closure machinery to every un-integrated
descendant, and cancel signals go to exactly the work that has not been merged.
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

from registry.normalization.content_hash import normalization_hash
from registry.normalization.gate_map import GATE_MAP_PATH, load_gate_map
from registry.normalization.loader import LEDGER_PATH, load_ledger
from registry.normalization.stale import NORMALIZATION_TRIGGER, cancel_signals, hash_bump_closure
from registry.state.closure import load_graph
from registry.state.model import WorkPackageState
from registry.state.store import StateStore

DECOY_TRIGGER = "PG-IK-001:PASS"
EVIDENCE = "sha256:" + "e" * 64

SEED_WP = "WP-DEP-01"
MIDDLE_WP = "WP-DEP-02"
LEAF_WP = "WP-DEP-03"


def _dependent_registry(path: Path) -> Path:
    """Write three WPs chained under the normalization staleness trigger.

    The seed declares `normalization_hash:CHANGED`; the other two inherit staleness
    transitively down the downstream edges. A decoy on an unrelated trigger proves
    the bump does not over-propagate.

    Args:
        path: Destination file.

    Returns:
        (Path): The file written.
    """
    entries = [
        {
            "req": "PLAN-DEP-01",
            "wp": SEED_WP,
            "stale_on": [NORMALIZATION_TRIGGER],
            "downstream": [MIDDLE_WP],
            "artifact": [{"id": "ART-DEP-01", "kind": "code", "path": "dep1.py"}],
        },
        {
            "req": "PLAN-DEP-02",
            "wp": MIDDLE_WP,
            "stale_on": [],
            "downstream": [LEAF_WP],
            "artifact": [{"id": "ART-DEP-02", "kind": "code", "path": "dep2.py"}],
        },
        {
            "req": "PLAN-DEP-03",
            "wp": LEAF_WP,
            "stale_on": [],
            "downstream": [],
            "artifact": [{"id": "ART-DEP-03", "kind": "code", "path": "dep3.py"}],
        },
        {
            "req": "PLAN-OTHER-01",
            "wp": "WP-OTHER-01",
            "stale_on": [DECOY_TRIGGER],
            "downstream": [],
            "artifact": [],
        },
    ]
    path.write_text(
        yaml.safe_dump({"version": 1, "spine_ref": "test", "entries": entries}),
        encoding="utf-8",
    )
    return path


def test_one_row_change_bumps_the_issued_hash() -> None:
    """The trigger's cause: editing one ledger row changes the hash."""
    ledger = load_ledger(LEDGER_PATH)
    gate_map = load_gate_map(GATE_MAP_PATH)
    before = normalization_hash(ledger, gate_map)

    bumped = copy.deepcopy(ledger)
    bumped["rows"][0]["winners"].append("FR-NEW-001")
    after = normalization_hash(bumped, gate_map)

    assert before != after


def test_bump_stales_exactly_three_descendants(tmp_path: Path) -> None:
    """Acceptance ③ — three descendants enter the closure, transitively."""
    graph = load_graph(_dependent_registry(tmp_path / "dep.yaml"))
    closure = hash_bump_closure(graph)

    assert closure.wps == {SEED_WP, MIDDLE_WP, LEAF_WP}
    assert closure.depth == {SEED_WP: 0, MIDDLE_WP: 1, LEAF_WP: 2}


def test_bump_does_not_touch_unrelated_triggers(tmp_path: Path) -> None:
    """A WP on a different trigger stays out of the bump's closure."""
    graph = load_graph(_dependent_registry(tmp_path / "dep.yaml"))
    assert "WP-OTHER-01" not in hash_bump_closure(graph).wps


def test_cancel_signal_reaches_only_unintegrated_work(tmp_path: Path) -> None:
    """The cancel signal goes to un-integrated descendants; integrated work is spared."""
    graph = load_graph(_dependent_registry(tmp_path / "dep.yaml"))
    store = StateStore(tmp_path / "state")
    store.transition(SEED_WP, WorkPackageState.ACTIVE, "spawn", EVIDENCE)
    store.transition(MIDDLE_WP, WorkPackageState.ACTIVE, "spawn", EVIDENCE)
    store.transition(MIDDLE_WP, WorkPackageState.INTEGRATED, "merge", EVIDENCE)
    # LEAF_WP has no record: never started, so still cancellable.

    signals = cancel_signals(hash_bump_closure(graph), store)

    assert signals == [SEED_WP, LEAF_WP]
    assert MIDDLE_WP not in signals


def test_integrated_descendant_is_still_in_the_closure(tmp_path: Path) -> None:
    """Excluded from cancellation is not excluded from staleness (05 §5.2 P-3 vs P-4)."""
    graph = load_graph(_dependent_registry(tmp_path / "dep.yaml"))
    assert MIDDLE_WP in hash_bump_closure(graph).wps
