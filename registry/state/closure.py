"""Transitive descendant closure over the registry's stale propagation axis.

`05` §5.2 P-2 is explicit that the propagation set is a transitive closure, not the set of direct
descendants: a gate flip invalidates the consumers of the consumers. Stopping one level deep
produces a set that looks plausible and silently leaves live work standing on an invalidated
basis, which is the failure mode `06` §4.4 calls out as stale propagation halting at step 1.

Edge model:
  seed edge  `stale_on[]` trigger match  — the work packages a trigger fires on directly.
  walk edge  `downstream[]` WP entries   — the "gate -> downstream consumer" edges of `05` P-2.

Contract-mediated propagation is deliberately NOT inferred from a package going stale. A stale
producer is not the same event as a MAJOR bump of the contract it produces; when a bump is what
actually happened, the caller passes a `CTR-*:MAJOR_BUMP` trigger and the seed match handles it.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path

import yaml

WP_PREFIX = "WP-"


@dataclass(frozen=True)
class ArtifactRef:
    """One artifact owned by a work package."""

    id: str
    kind: str
    path: str
    wp: str


@dataclass(frozen=True)
class StaleClosure:
    """Result of propagating one trigger through the registry.

    Attributes:
        trigger: The trigger that was injected.
        wps: Every affected work package, seeds included.
        artifacts: Every artifact owned by an affected package.
        depth: Hop count per package; seeds are 0. A one-level-deep implementation cannot
            produce a depth above 1, which is what makes shallow implementations detectable.
    """

    trigger: str
    wps: frozenset[str]
    artifacts: tuple[ArtifactRef, ...]
    depth: dict[str, int]


class RegistryGraph:
    """Per-work-package view of the registry axes the closure walks.

    Registry records are keyed by requirement, so several records share one `wp`. The axes are
    unioned across those records; `CI-14c` is what enforces that they agree in the first place,
    and duplicating that check here would put the rule in two places.
    """

    def __init__(self) -> None:
        self.triggers: dict[str, set[str]] = {}
        self.downstream: dict[str, set[str]] = {}
        self.artifacts: dict[str, list[ArtifactRef]] = {}

    def add_entry(self, entry: dict[str, object]) -> None:
        """Fold one registry record into the graph.

        Args:
            entry: A record from `registry/traceability.yaml`.
        """
        wp = entry.get("wp")
        if not isinstance(wp, str) or not wp.startswith(WP_PREFIX):
            return

        triggers = self.triggers.setdefault(wp, set())
        for trigger in _string_list(entry.get("stale_on")):
            triggers.add(trigger)

        edges = self.downstream.setdefault(wp, set())
        for target in _string_list(entry.get("downstream")):
            if target.startswith(WP_PREFIX):
                edges.add(target)

        owned = self.artifacts.setdefault(wp, [])
        raw_artifacts = entry.get("artifact")
        if isinstance(raw_artifacts, list):
            for item in raw_artifacts:
                if not isinstance(item, dict):
                    continue
                ref = ArtifactRef(
                    id=str(item.get("id", "")),
                    kind=str(item.get("kind", "")),
                    path=str(item.get("path", "")),
                    wp=wp,
                )
                if ref not in owned:
                    owned.append(ref)

    def seeds(self, trigger: str) -> set[str]:
        """Find the work packages a trigger fires on directly.

        Args:
            trigger: A `stale_on` trigger such as `PG-SAFE-001:FAIL_BLOCKING`.

        Returns:
            (set[str]): Work packages declaring that trigger.
        """
        return {wp for wp, triggers in self.triggers.items() if trigger in triggers}


def _string_list(value: object) -> list[str]:
    """Coerce a registry axis to a list of strings.

    Args:
        value: Raw axis value; may be absent or null.

    Returns:
        (list[str]): The string elements, or an empty list.
    """
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def load_graph(path: Path) -> RegistryGraph:
    """Build a graph from a traceability registry file.

    Args:
        path: Path to `registry/traceability.yaml` or a fixture in the same shape.

    Returns:
        (RegistryGraph): Graph over the stale and downstream axes.
    """
    with path.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    graph = RegistryGraph()
    entries = document.get("entries", []) if isinstance(document, dict) else []
    for entry in entries:
        if isinstance(entry, dict):
            graph.add_entry(entry)
    return graph


def descendant_closure(graph: RegistryGraph, trigger: str) -> StaleClosure:
    """Enumerate every work package invalidated by a trigger, transitively.

    Breadth-first over `downstream` edges from the seed set. The visited set both terminates
    cycles in the registry graph and keeps the first (shortest) depth recorded for each package.

    Args:
        graph: Graph built by `load_graph`.
        trigger: The gate state change or contract bump being injected.

    Returns:
        (StaleClosure): Affected packages, their artifacts, and hop depth per package.
    """
    depth: dict[str, int] = {}
    queue: deque[tuple[str, int]] = deque()
    for seed in sorted(graph.seeds(trigger)):
        depth[seed] = 0
        queue.append((seed, 0))

    while queue:
        wp, hops = queue.popleft()
        for target in sorted(graph.downstream.get(wp, set())):
            if target in depth:
                continue
            depth[target] = hops + 1
            queue.append((target, hops + 1))

    artifacts: list[ArtifactRef] = []
    for wp in sorted(depth):
        artifacts.extend(graph.artifacts.get(wp, []))

    return StaleClosure(
        trigger=trigger,
        wps=frozenset(depth),
        artifacts=tuple(artifacts),
        depth=depth,
    )
