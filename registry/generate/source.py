"""Project `registry/traceability.yaml` onto the per-work-package view.

The registry is keyed by requirement, so one work package is spread across as
many records as it implements requirements. Every generated artefact in this
package needs the opposite shape, and collapsing records into a package is the
one place where that regrouping may happen — doing it per generator would let
two generators disagree about what a package is.

`06` §5 `CI-14c` splits the fields into three classes. This module enforces the
(A) class while regrouping: those fields belong to the package, not the record,
so records sharing a `wp` must agree on them exactly. Silently taking the first
record's value would forge a manifest that no record actually asserts, and the
drift it hides (notably `downstream[]`) moves the stale-propagation descendant
set — the failure would surface only once every downstream package sits on top
of it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REGISTRY_PATH = Path("registry/traceability.yaml")
BUILD_DIR = Path("registry/build")

# `wp` is a real package id everywhere except these two sentinels, which mean
# "no package owns this requirement" and therefore have no manifest.
NON_PACKAGE_WP = frozenset({"OUT", "DEFERRED"})

# `CI-14c` (A): owned by the package. Records sharing a `wp` must agree.
PACKAGE_FIELDS = (
    "workflow",
    "exec_class",
    "phases",
    "owns",
    "gate",
    "negative_branch",
    "stale_on",
    "downstream",
    "targets",
    "terminal",
    "env_hash",
)

Record = dict[str, Any]


class RegistryDriftError(Exception):
    """Raised when records of one work package disagree on a package-level field."""


@dataclass(frozen=True)
class WorkPackage:
    """One work package as the registry asserts it, regrouped from its records.

    Attributes:
        wp_id: Package id issued by `02a`..`02d`.
        requirements: Requirement ids this package implements, sorted.
        workflow: Shape token, or None when the package is multi-stage.
        exec_class: Execution class, or None when the package is multi-stage.
        phases: Ordered stages, or None when the package is single-stage.
        owns: `{glob, mode}` entries; the union of stage lists when multi-stage.
        gates: Gate ids, sorted.
        consumes: Contract ids consumed — the union over records, since
            `contract.consumes[]` is a (C)-class field that legitimately
            differs per requirement.
        produces: Contract ids produced.
        stale_on: Stale-propagation triggers.
        downstream: Successor ids as declared; may name packages, contracts or
            artefacts.
        normalization_hash: Normalization-ledger hash, filled by `WP-N1-04`.
        env_hash: Environment hash, issued by `WP-ENV-04`.
    """

    wp_id: str
    requirements: list[str]
    workflow: str | None
    exec_class: str | None
    phases: list[Record] | None
    owns: list[Record]
    gates: list[str]
    consumes: list[str]
    produces: list[str]
    stale_on: list[str]
    downstream: list[str]
    normalization_hash: str | None
    env_hash: str | None
    records: list[Record] = field(repr=False)

    @property
    def is_multi_stage(self) -> bool:
        """Report whether execution meaning changes inside this package.

        Returns:
            bool: True when the package declares `phases[]` instead of scalars.
        """
        return self.phases is not None

    @property
    def stage_owns(self) -> list[Record]:
        """Collect every owned path across every stage.

        `CI-02` expands multi-stage packages through `phases[].owns`, so the
        ownership view must see stage-local paths, not only the package-level
        union.

        Returns:
            list[Record]: `{glob, mode}` entries, package level plus per stage.
        """
        collected = list(self.owns)
        for stage in self.phases or []:
            collected.extend(stage.get("owns") or [])
        return _dedupe_owns(collected)


def load_registry(path: Path) -> dict[str, Any]:
    """Read the traceability registry.

    Args:
        path: Path to `registry/traceability.yaml`.

    Returns:
        dict[str, Any]: The parsed document, with `entries` as a list.
    """
    with path.open(encoding="utf-8") as handle:
        document: dict[str, Any] = yaml.safe_load(handle)
    return document


def canonical_json(payload: Any) -> str:
    """Serialize a generated artefact in the one byte-stable form.

    Key order is imposed rather than inherited, so the output does not depend
    on the insertion order of any dict built upstream.

    Args:
        payload: JSON-serializable object.

    Returns:
        str: Pretty-printed JSON with sorted keys and a trailing newline.
    """
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def registry_digest(document: dict[str, Any]) -> str:
    """Hash the registry's parsed content.

    The digest covers the parsed document, not the file bytes, so YAML
    comments, key order and whitespace are transparent to it while any change
    to a value changes it. That is the intended sensitivity: the registry is
    data, and reformatting it is not a regeneration event.

    Args:
        document: Parsed registry document.

    Returns:
        str: `sha256:<hex>`.
    """
    blob = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def group_by_work_package(document: dict[str, Any]) -> list[WorkPackage]:
    """Regroup requirement-keyed records into work packages.

    Args:
        document: Parsed registry document.

    Returns:
        list[WorkPackage]: One entry per real package id, sorted by id.

    Raises:
        RegistryDriftError: If records sharing a `wp` disagree on a (A)-class
            field, or declare two different normalization hashes.
    """
    grouped: dict[str, list[Record]] = {}
    for record in document["entries"]:
        wp_id = record["wp"]
        if wp_id in NON_PACKAGE_WP:
            continue
        grouped.setdefault(wp_id, []).append(record)

    return [_build(wp_id, grouped[wp_id]) for wp_id in sorted(grouped)]


def _build(wp_id: str, records: list[Record]) -> WorkPackage:
    """Collapse one package's records into a single view.

    Args:
        wp_id: The shared package id.
        records: Every record whose `wp` equals `wp_id`.

    Returns:
        WorkPackage: The collapsed view.

    Raises:
        RegistryDriftError: On (A)-class disagreement.
    """
    agreed = {name: _agree(wp_id, name, records) for name in PACKAGE_FIELDS}
    phases = agreed["phases"]
    consumes = {contract for record in records for contract in record["contract"]["consumes"]}

    return WorkPackage(
        wp_id=wp_id,
        requirements=sorted(record["req"] for record in records),
        workflow=agreed["workflow"],
        exec_class=agreed["exec_class"],
        phases=list(phases) if phases else None,
        owns=_dedupe_owns(agreed["owns"] or []),
        gates=sorted(agreed["gate"] or []),
        consumes=sorted(consumes),
        produces=sorted(_agree(wp_id, "produces", records, nested="contract") or []),
        stale_on=sorted(agreed["stale_on"] or []),
        downstream=sorted(agreed["downstream"] or []),
        normalization_hash=_single_normalization(wp_id, records),
        env_hash=agreed["env_hash"],
        records=records,
    )


def _agree(wp_id: str, name: str, records: list[Record], nested: str | None = None) -> Any:
    """Return the one value all records assert for a package-level field.

    Args:
        wp_id: Package id, for the error message.
        name: Field name.
        records: The package's records.
        nested: Parent key when the field lives under one (`contract`).

    Returns:
        Any: The agreed value, or None when no record declares the field.

    Raises:
        RegistryDriftError: If the records assert more than one value.
    """
    seen: dict[str, Any] = {}
    for record in records:
        holder = record[nested] if nested else record
        value = holder.get(name)
        seen[json.dumps(value, ensure_ascii=False, sort_keys=True)] = value
    if len(seen) > 1:
        raise RegistryDriftError(
            f"{wp_id}: records disagree on package-level field {name!r}: "
            f"{sorted(seen)} (CI-14c class A)"
        )
    return next(iter(seen.values()), None)


def _single_normalization(wp_id: str, records: list[Record]) -> str | None:
    """Reduce per-requirement normalization hashes to the package's slot.

    `normalization` is a (B)-class field — it is stated per requirement — but a
    package is built against one normalization ledger. One distinct non-null
    value is that ledger; two would mean the package was built against two, and
    no manifest can express which.

    Args:
        wp_id: Package id, for the error message.
        records: The package's records.

    Returns:
        str | None: The hash, or None while `WP-N1-04` has not issued one.

    Raises:
        RegistryDriftError: If two different non-null hashes are declared.
    """
    hashes = {record["normalization"] for record in records if record.get("normalization")}
    if len(hashes) > 1:
        raise RegistryDriftError(
            f"{wp_id}: records declare {len(hashes)} different normalization hashes "
            f"{sorted(hashes)}; a package is built against one ledger"
        )
    return next(iter(hashes), None)


def _dedupe_owns(entries: Iterable[Record]) -> list[Record]:
    """Drop repeated `{glob, mode}` pairs and impose a stable order.

    Args:
        entries: Ownership entries, possibly repeated across records or stages.

    Returns:
        list[Record]: Unique entries sorted by glob then mode.
    """
    unique = {(entry["glob"], entry["mode"]) for entry in entries}
    return [{"glob": glob, "mode": mode} for glob, mode in sorted(unique)]
