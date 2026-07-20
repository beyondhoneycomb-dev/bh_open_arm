"""Build the five derived indexes over the traceability registry.

`06` §4.4 step 1 enumerates a stale set by walking reverse indexes. Those
reverse indexes are these files: without them the propagation described in the
plan has nothing to walk and stops at step 1.

Every index carries the digest of the registry content it was derived from.
Payload alone would not satisfy "one changed bit gives a different index" — a
change to a field a given index does not project would leave that file byte
identical and make it silently stale against its source. The digest binds each
file to the exact registry content that produced it.
"""

from __future__ import annotations

from typing import Any

from registry.generate.source import Record, WorkPackage, canonical_json

SCHEMA_VERSION = 1

# `downstream[]` may name packages, contracts (`CTR-*`) or artefacts (`ART-*`).
# Only package ids are edges in the descendant walk; the other two are leaves
# that the contract index and the artefact axis cover instead.
_PACKAGE_PREFIX = "WP-"


def build_req_index(packages: list[WorkPackage]) -> dict[str, str]:
    """Map each requirement to the work package that implements it.

    Args:
        packages: Collapsed registry views.

    Returns:
        dict[str, str]: Requirement id to work-package id.
    """
    return {
        requirement: package.wp_id for package in packages for requirement in package.requirements
    }


def build_wp_index(packages: list[WorkPackage]) -> dict[str, Record]:
    """Map each work package to its requirements and its axes.

    `contract_refs` appears here and nowhere else: it is the derived view of
    `consumes ∪ produces` (`06` §2.2), computed by this generator rather than
    stored, so that no record can assert a contract reference the two source
    axes do not already carry.

    Args:
        packages: Collapsed registry views.

    Returns:
        dict[str, Record]: Work-package id to `{requirements, axes,
        contract_refs}`.
    """
    index: dict[str, Record] = {}
    for package in packages:
        axes: Record = {
            "owns": package.owns,
            "gates": package.gates,
            "consumes": package.consumes,
            "produces": package.produces,
            "stale_on": package.stale_on,
            "downstream": package.downstream,
            "normalization_hash": package.normalization_hash,
            "env_hash": package.env_hash,
        }
        if package.is_multi_stage:
            axes["phases"] = package.phases
        else:
            axes["workflow"] = package.workflow
            axes["exec_class"] = package.exec_class
        index[package.wp_id] = {
            "requirements": package.requirements,
            "axes": axes,
            "contract_refs": sorted(set(package.consumes) | set(package.produces)),
        }
    return index


def build_glob_index(packages: list[WorkPackage]) -> dict[str, list[Record]]:
    """Map each owned glob to the packages that own it and in which mode.

    The value is a list because ownership is exclusive at a point in time, not
    over all time: a sequential handover (`WP-1-02` to `WP-1-03`) legitimately
    puts two packages on one glob, and `CI-02` distinguishes that from a real
    overlap. Collapsing to a single owner here would hide the handover.

    Args:
        packages: Collapsed registry views.

    Returns:
        dict[str, list[Record]]: Glob to `[{wp, mode}]`, sorted.
    """
    index: dict[str, list[Record]] = {}
    for package in packages:
        for entry in package.stage_owns:
            index.setdefault(entry["glob"], []).append({"wp": package.wp_id, "mode": entry["mode"]})
    return {
        glob: sorted(owners, key=lambda owner: (owner["wp"], owner["mode"]))
        for glob, owners in index.items()
    }


def build_contract_index(packages: list[WorkPackage]) -> dict[str, Record]:
    """Map each contract to its producing and consuming packages.

    `producers` is a list although `CI-03` requires exactly one. The index has
    to be buildable from a registry that currently violates `CI-03`, otherwise
    the checker that detects the violation could never be built; expressing the
    producer set makes `len(producers) != 1` the checker's whole predicate.

    Args:
        packages: Collapsed registry views.

    Returns:
        dict[str, Record]: Contract id to `{producers, consumers}`.
    """
    index: dict[str, Record] = {}
    for package in packages:
        for contract in package.produces:
            index.setdefault(contract, {"producers": [], "consumers": []})["producers"].append(
                package.wp_id
            )
        for contract in package.consumes:
            index.setdefault(contract, {"producers": [], "consumers": []})["consumers"].append(
                package.wp_id
            )
    return {
        contract: {"producers": sorted(sides["producers"]), "consumers": sorted(sides["consumers"])}
        for contract, sides in index.items()
    }


def build_gate_index(packages: list[WorkPackage]) -> dict[str, Record]:
    """Map each gate to the packages hanging off it and their descendants.

    A package is attached to a gate either by declaring it in `gates` or by
    naming it as a stale trigger. Descendants are the transitive closure over
    `downstream` from that attachment set — transitive, because `06` §4.4 step
    1 has to enumerate the whole set, and a one-hop walk would leave the far
    side of the graph live on top of a superseded measurement.

    Args:
        packages: Collapsed registry views.

    Returns:
        dict[str, Record]: Gate id to `{work_packages, descendants}`.
    """
    successors = {
        package.wp_id: [
            successor for successor in package.downstream if successor.startswith(_PACKAGE_PREFIX)
        ]
        for package in packages
    }

    attached: dict[str, set[str]] = {}
    for package in packages:
        for gate in package.gates:
            attached.setdefault(gate, set()).add(package.wp_id)
        for trigger in package.stale_on:
            attached.setdefault(trigger.split(":", 1)[0], set()).add(package.wp_id)

    return {
        gate: {
            "work_packages": sorted(seeds),
            "descendants": sorted(_closure(seeds, successors) - seeds),
        }
        for gate, seeds in attached.items()
    }


def check_index_inverse(req_index: dict[str, str], wp_index: dict[str, Record]) -> list[str]:
    """Verify that the requirement and work-package indexes are inverses.

    Stale propagation walks requirement to package and package to requirement
    in the same pass. If only one direction holds, the walk enumerates a
    truncated descendant set while reporting success — so a one-directional
    pair is rejected rather than repaired.

    Args:
        req_index: Requirement id to work-package id.
        wp_index: Work-package id to `{requirements, ...}`.

    Returns:
        list[str]: One message per broken pairing; empty when mutually inverse.
    """
    broken: list[str] = []
    for requirement, wp_id in sorted(req_index.items()):
        entry = wp_index.get(wp_id)
        if entry is None:
            broken.append(f"{requirement} -> {wp_id}: work package absent from wp_index")
        elif requirement not in entry["requirements"]:
            broken.append(f"{requirement} -> {wp_id}: wp_index does not list it back")

    for wp_id, entry in sorted(wp_index.items()):
        for requirement in entry["requirements"]:
            mapped = req_index.get(requirement)
            if mapped is None:
                broken.append(f"{wp_id} -> {requirement}: requirement absent from req_index")
            elif mapped != wp_id:
                broken.append(f"{wp_id} -> {requirement}: req_index maps it to {mapped}")
    return broken


def render_indexes(packages: list[WorkPackage], source_digest: str) -> dict[str, str]:
    """Render all five indexes as build-relative path to file text.

    Args:
        packages: Collapsed registry views.
        source_digest: Digest of the registry content being projected.

    Returns:
        dict[str, str]: Build-relative filename to serialized index.

    Raises:
        ValueError: If the requirement and work-package indexes are not
            mutual inverses.
    """
    req_index = build_req_index(packages)
    wp_index = build_wp_index(packages)
    broken = check_index_inverse(req_index, wp_index)
    if broken:
        raise ValueError("req_index and wp_index are not mutual inverses: " + "; ".join(broken))

    payloads: dict[str, Any] = {
        "req_index.json": req_index,
        "wp_index.json": wp_index,
        "glob_index.json": build_glob_index(packages),
        "contract_index.json": build_contract_index(packages),
        "gate_index.json": build_gate_index(packages),
    }
    return {
        name: canonical_json(
            {"schema_version": SCHEMA_VERSION, "source_digest": source_digest, "index": payload}
        )
        for name, payload in payloads.items()
    }


def _closure(seeds: set[str], successors: dict[str, list[str]]) -> set[str]:
    """Walk every successor edge reachable from the seed set.

    Args:
        seeds: Starting work-package ids.
        successors: Work-package id to its downstream package ids.

    Returns:
        set[str]: Seeds plus everything reachable from them.
    """
    reached = set(seeds)
    pending = list(seeds)
    while pending:
        current = pending.pop()
        for successor in successors.get(current, []):
            if successor not in reached:
                reached.add(successor)
                pending.append(successor)
    return reached
