"""Acceptance ② — transitive descendant closure over the stale_on axis.

The load-bearing test is the depth-3 chain: a one-level implementation returns a set that looks
reasonable and is wrong, so the fixture is built deep enough that shallowness is visible.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from registry.state.closure import RegistryGraph, descendant_closure, load_graph

TRIGGER = "PG-SAFE-001:FAIL_BLOCKING"
UNRELATED_TRIGGER = "PG-IK-001:PASS"
REAL_REGISTRY = Path("registry/traceability.yaml")
EXPECTED_WP_COUNT = 177


def _entry(
    req: str,
    wp: str,
    stale_on: list[str],
    downstream: list[str],
    artifacts: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    """Build one registry record.

    Args:
        req: Requirement id.
        wp: Work package id.
        stale_on: Stale triggers.
        downstream: Downstream references.
        artifacts: Artifact entries.

    Returns:
        (dict[str, object]): The record.
    """
    return {
        "req": req,
        "wp": wp,
        "stale_on": stale_on,
        "downstream": downstream,
        "artifact": artifacts or [],
    }


def _write_registry(path: Path, entries: list[dict[str, object]]) -> Path:
    """Write a fixture registry file.

    Args:
        path: Destination file.
        entries: Records to write.

    Returns:
        (Path): The file written.
    """
    path.write_text(
        yaml.safe_dump({"version": 1, "spine_ref": "test", "entries": entries}),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def chain_graph(tmp_path: Path) -> RegistryGraph:
    """Build a four-deep propagation chain with a decoy branch.

    Returns:
        (RegistryGraph): Graph whose closure from TRIGGER is A -> B -> C -> D.
    """
    entries = [
        _entry(
            "PLAN-BOOT-01",
            "WP-A-01",
            [TRIGGER],
            ["WP-B-01"],
            [{"id": "ART-A", "kind": "code", "path": "a.py"}],
        ),
        _entry(
            "PLAN-BOOT-02",
            "WP-B-01",
            [],
            ["WP-C-01"],
            [{"id": "ART-B", "kind": "code", "path": "b.py"}],
        ),
        _entry(
            "PLAN-BOOT-03",
            "WP-C-01",
            [],
            ["WP-D-01"],
            [{"id": "ART-C", "kind": "code", "path": "c.py"}],
        ),
        _entry(
            "PLAN-BOOT-04",
            "WP-D-01",
            [],
            [],
            [{"id": "ART-D", "kind": "code", "path": "d.py"}],
        ),
        # Fires on a different trigger and must never enter this closure.
        _entry("PLAN-BOOT-05", "WP-Z-01", [UNRELATED_TRIGGER], ["WP-Y-01"]),
        _entry("PLAN-BOOT-06", "WP-Y-01", [], []),
    ]
    return load_graph(_write_registry(tmp_path / "chain.yaml", entries))


def test_closure_reaches_the_deepest_descendant(chain_graph: RegistryGraph) -> None:
    """Acceptance ② — the full transitive set, not the direct descendants."""
    closure = descendant_closure(chain_graph, TRIGGER)
    assert closure.wps == {"WP-A-01", "WP-B-01", "WP-C-01", "WP-D-01"}
    assert closure.depth == {"WP-A-01": 0, "WP-B-01": 1, "WP-C-01": 2, "WP-D-01": 3}


def test_closure_excludes_packages_on_other_triggers(chain_graph: RegistryGraph) -> None:
    """Over-propagation is a defect too: an unrelated trigger's subtree stays out."""
    closure = descendant_closure(chain_graph, TRIGGER)
    assert "WP-Z-01" not in closure.wps
    assert "WP-Y-01" not in closure.wps


def test_closure_enumerates_descendant_artifacts(chain_graph: RegistryGraph) -> None:
    """`06` §4.4 step 1 requires the descendant artifact list, not just the package list."""
    closure = descendant_closure(chain_graph, TRIGGER)
    assert [item.id for item in closure.artifacts] == ["ART-A", "ART-B", "ART-C", "ART-D"]


def test_violation_fixture_one_level_implementation_is_rejected(
    chain_graph: RegistryGraph,
) -> None:
    """A closure that stops at the direct descendants must fail this suite's assertion.

    This is the fixture the acceptance criterion names. `_one_level_closure` is what a plausible
    wrong implementation looks like; if the expected set above could be satisfied by it, the
    transitivity requirement would not be tested by anything.
    """
    shallow = _one_level_closure(chain_graph, TRIGGER)
    full = descendant_closure(chain_graph, TRIGGER).wps

    assert shallow == {"WP-A-01", "WP-B-01"}
    assert shallow != full
    assert "WP-D-01" not in shallow
    assert "WP-D-01" in full


def test_closure_terminates_on_a_cycle(tmp_path: Path) -> None:
    """A cyclic downstream graph must terminate rather than loop."""
    entries = [
        _entry("PLAN-BOOT-01", "WP-A-01", [TRIGGER], ["WP-B-01"]),
        _entry("PLAN-BOOT-02", "WP-B-01", [], ["WP-C-01"]),
        _entry("PLAN-BOOT-03", "WP-C-01", [], ["WP-A-01"]),
    ]
    graph = load_graph(_write_registry(tmp_path / "cycle.yaml", entries))

    closure = descendant_closure(graph, TRIGGER)
    assert closure.wps == {"WP-A-01", "WP-B-01", "WP-C-01"}
    assert closure.depth["WP-A-01"] == 0


def test_axes_are_unioned_across_records_of_one_package(tmp_path: Path) -> None:
    """Records are keyed by requirement, so one package spans several of them."""
    entries = [
        _entry("PLAN-BOOT-01", "WP-A-01", [TRIGGER], ["WP-B-01"]),
        _entry("PLAN-BOOT-02", "WP-A-01", [], ["WP-C-01"]),
        _entry("PLAN-BOOT-03", "WP-B-01", [], []),
        _entry("PLAN-BOOT-04", "WP-C-01", [], []),
    ]
    graph = load_graph(_write_registry(tmp_path / "multi.yaml", entries))

    closure = descendant_closure(graph, TRIGGER)
    assert closure.wps == {"WP-A-01", "WP-B-01", "WP-C-01"}


def test_contract_bump_trigger_seeds_the_closure(tmp_path: Path) -> None:
    """A MAJOR bump is a trigger like any other; the same walk applies."""
    entries = [
        _entry("PLAN-BOOT-01", "WP-A-01", ["CTR-PRIM:MAJOR_BUMP"], ["WP-B-01"]),
        _entry("PLAN-BOOT-02", "WP-B-01", [], []),
    ]
    graph = load_graph(_write_registry(tmp_path / "ctr.yaml", entries))

    assert descendant_closure(graph, "CTR-PRIM:MAJOR_BUMP").wps == {"WP-A-01", "WP-B-01"}


def test_unknown_trigger_yields_an_empty_closure(chain_graph: RegistryGraph) -> None:
    assert descendant_closure(chain_graph, "PG-NOPE-999:PASS").wps == frozenset()


def test_real_registry_loads_into_the_graph() -> None:
    """The calculator runs against the shipped registry, not only against fixtures."""
    graph = load_graph(REAL_REGISTRY)
    assert len(graph.triggers) == EXPECTED_WP_COUNT
    assert sum(len(edges) for edges in graph.downstream.values()) > 0
    # Must not raise on real data, whatever the axis population currently is.
    descendant_closure(graph, TRIGGER)


def _one_level_closure(graph: RegistryGraph, trigger: str) -> set[str]:
    """Compute seeds plus their direct descendants only.

    This is the shallow implementation the acceptance criterion requires be rejected. It lives
    in the test because it is a fixture, not a code path anything should be able to call.

    Args:
        graph: Graph to walk.
        trigger: Trigger to seed from.

    Returns:
        (set[str]): Seeds and one hop, and nothing beyond.
    """
    seeds = graph.seeds(trigger)
    result = set(seeds)
    for seed in seeds:
        result |= graph.downstream.get(seed, set())
    return result
