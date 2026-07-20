"""Seed `registry/traceability.yaml` from the planning and specification corpus.

This runs once, at bootstrap. After it lands the registry is canonical and the
prose is a view of it (`05` §0.1); re-running is how the reconciliation report
is regenerated, not how the registry is maintained.

What this refuses to do is as important as what it does. Where the corpus does
not state a fact, the record says so — `wp: DEFERRED` for an unresolved owner,
empty axes for undeclared ones, `null` for hashes issued by downstream waves.
Filling those with plausible values would produce a registry that validates,
reports green, and is wrong in ways no check can see.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from registry.ingest.catalog import CONTRACT_ID, PG_ID, WP_ID, CatalogEntry
from registry.ingest.catalog import parse_all as parse_catalogs
from registry.ingest.markdown import all_tables, find_pipe_defects, plain_text
from registry.ingest.resolve import (
    DEFERRED,
    RULE_AMBIGUOUS,
    RULE_COVERAGE,
    RULE_PLAN_AXIS,
    RULE_UNCITED,
    Assignment,
    fill_coverage,
    read_doc06_assignments,
    resolve,
    unregistered_packages,
)
from registry.ingest.spec import Requirement
from registry.ingest.spec import parse_all as parse_spec

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = 1
BOOT_BAND = "BOOT"

# Shape determines execution class for every shape but SHAPE-HG, where the
# residual (holding the arm vs judging a result) is real because the two carry
# different cancel policies (`00` §4.0).
SHAPE_TO_EXEC_CLASS = {
    "SHAPE-CF": "AI-offline",
    "SHAPE-IM": "AI-offline",
    "SHAPE-IG": "AI-offline",
    "SHAPE-MS": "AI-on-HW",
}
# A stage that occupies the rig latches before it cancels: with no holding
# brake, "let the current step finish" means the arm keeps moving.
LATCHING_CLASSES = ("AI-on-HW", "Human-assisted-HW")

_OWNS_MAP_MODES = ("EXCLUSIVE", "CONTRACT_FROZEN", "SHARED_APPEND", "GENERATED")


@dataclass
class BuildReport:
    """Counts and locations the seeding produced, for the reconciliation report.

    Attributes:
        requirements: Requirements declared by the specification.
        packages: Work packages issued by the catalogs.
        assignment_rules: How many requirements each resolution rule decided.
        undeclared_priority: Requirements whose priority cell is not M/S/C.
        undeclared_tag: Requirements whose status marker is outside the vocabulary.
        packages_without_records: Issued packages no requirement reaches.
        packages_without_acceptance: Packages declaring no numbered acceptance item.
        multi_stage_packages: Packages the catalogs declared with several stages.
        pipe_defects: Table rows holding an unescaped pipe inside a code span.
    """

    requirements: int = 0
    packages: int = 0
    assignment_rules: dict[str, int] = field(default_factory=dict)
    undeclared_priority: list[str] = field(default_factory=list)
    undeclared_tag: list[str] = field(default_factory=list)
    packages_without_records: list[str] = field(default_factory=list)
    packages_without_acceptance: list[str] = field(default_factory=list)
    multi_stage_packages: list[str] = field(default_factory=list)
    pipe_defects: list[str] = field(default_factory=list)


def read_glob_ownership(registry_doc: Path) -> dict[str, list[dict[str, str]]]:
    """Read the per-package glob ownership declared in `06` §3.2.

    Only §3.2 is used, because it names an owning *package*. The §3.3 map
    assigns globs to a *band*, and expanding a band's glob onto every package
    in it would manufacture ownership overlaps that CI-02 would then report as
    real conflicts.

    Args:
        registry_doc: Path to `06-추적성-레지스트리.md`.

    Returns:
        (dict) Work-package id to its `{glob, mode}` entries.
    """
    ownership: dict[str, list[dict[str, str]]] = {}
    for table in all_tables(registry_doc):
        glob_column = table.column_index("glob")
        mode_column = table.column_index("모드")
        owner_column = table.column_index("소유 WP")
        if glob_column is None or mode_column is None or owner_column is None:
            continue
        if table.column_index("소유 WP대역") is not None:
            continue
        for row in table.rows:
            mode = next(
                (value for value in _OWNS_MAP_MODES if value in plain_text(row[mode_column])), ""
            )
            if not mode:
                continue
            # One cell may name several paths (`06`:377 lists a calibration
            # schema module and its JSON side by side). Kept whole, the pair
            # becomes a single glob that matches nothing, and the overlap check
            # silently stops seeing either file.
            for glob in (part.strip() for part in plain_text(row[glob_column]).split(",")):
                if not glob:
                    continue
                for owner in WP_ID.findall(plain_text(row[owner_column])):
                    ownership.setdefault(owner, []).append({"glob": glob, "mode": mode})
    return ownership


def read_contract_producers(plan_dir: Path) -> dict[str, str]:
    """Read the declared producer of each contract.

    Producers come from the contract table, not from contract ids mentioned in
    a package's output column. The distinction is the same one that separates
    citation from ownership for requirements: a package naming `CTR-ACT@v1`
    among its outputs may be consuming it, extending it, or merely referring to
    it, and reading mentions as declarations manufactures a second producer.
    CI-03 then reports a violation that the corpus never contained.

    `01` §6.2 and `06` §4.1 both carry the table and agree on all thirteen
    entries, so either is authoritative; both are read and a disagreement is
    surfaced by returning the first and letting `CI-03` compare.

    Args:
        plan_dir: Directory holding the planning documents.

    Returns:
        (dict) Contract id (with `@v1`) to its declared producing package.
    """
    producers: dict[str, str] = {}
    for name in ("01-의존성-DAG-및-병렬화.md", "06-추적성-레지스트리.md"):
        document = plan_dir / name
        if not document.exists():
            continue
        for table in all_tables(document):
            id_column = table.column_index("계약 ID")
            owner_column = table.column_index("소유 WP", "producer")
            if id_column is None or owner_column is None:
                continue
            for row in table.rows:
                found = re.search(r"\bCTR-[A-Z]+\b", plain_text(row[id_column]))
                owners = WP_ID.findall(plain_text(row[owner_column]))
                if found and len(owners) == 1:
                    producers.setdefault(f"{found.group(0)}@v1", owners[0])
    return producers


def _phases_for(entry: CatalogEntry) -> list[dict[str, Any]]:
    """Expand a multi-stage catalog entry into ordered phase objects.

    The catalogs write stages as several tokens in one cell. Where the shape
    and class token counts differ, the shorter is extended by deriving class
    from shape, which is well-defined for every shape but `SHAPE-HG`; an
    underspecified `SHAPE-HG` stage keeps the entry's last declared class
    rather than inventing one.
    """
    shapes = list(entry.workflows) or ["SHAPE-CF"]
    classes = list(entry.exec_classes)
    # A package may declare two classes against one shape, or the reverse. The
    # stage count is the longer list; the shorter one is extended rather than
    # truncated, because dropping a stage loses the boundary whose cancel
    # policy differs, which is the only reason phases exist.
    while len(shapes) < len(classes):
        shapes.append(shapes[-1])
    phases: list[dict[str, Any]] = []

    for index, shape in enumerate(shapes):
        if index < len(classes):
            exec_class = classes[index]
        else:
            exec_class = SHAPE_TO_EXEC_CLASS.get(shape) or (
                classes[-1] if classes else "AI-offline"
            )
        phases.append(
            {
                "workflow": shape,
                "exec_class": exec_class,
                "owns": [],
                "cancel_policy": (
                    "latch-to-hold" if exec_class in LATCHING_CLASSES else "finish-step"
                ),
                "after": index - 1 if index else None,
            }
        )
    return phases


def _gates_for(entry: CatalogEntry) -> list[str]:
    """Collect the gate ids a package is judged by.

    Measurement gates are read from the acceptance text; acceptance checks are
    derived positionally (`06` §2.4a). A bare `PG-RT-001` is dropped rather
    than recorded: it is not a gate id in this position (CI-11b), and the
    catalogs use it legitimately as a family reference in the same prose.
    """
    measurement = [
        gate for gate in dict.fromkeys(PG_ID.findall(entry.acceptance_text)) if gate != "PG-RT-001"
    ]
    return measurement + list(entry.derived_cg_ids())


def _evidence_artifacts(gates: list[str]) -> list[dict[str, str]]:
    """Give every derived acceptance check its evidence path.

    `06` §2.4a fixes the path: each derived `CG-*` owns
    `registry/build/evidence/<CG-id>/`. CI-04b rejects a `CG-*` with no
    declared evidence, and the reason is stated in `06` §2.3 — a package
    defines its own acceptance checks, so referee and player are the same, and
    the only thing keeping that honest is a required observable artifact.

    Args:
        gates: Gate ids the package is judged by.

    Returns:
        (list) Artifact entries, one per acceptance check.
    """
    return [
        {
            "id": f"ART-EVIDENCE-{gate[3:].upper().replace('-', '')}",
            "kind": "report",
            "path": f"registry/build/evidence/{gate}/",
        }
        for gate in gates
        if gate.startswith("CG-")
    ]


def _negative_branches_for(entry: CatalogEntry, gates: list[str]) -> list[dict[str, str]]:
    """Give every gate at least one designed failure path.

    `CG-*` is PASS/FAIL binary, so its only branch is `FAIL` (CI-05e rejects
    any other value on one). `PG-*` carries the five-state machine, and CI-05c
    requires a non-terminal state, so the catalogs' negative-branch prose is
    attached to a `RETRY_WITH_VARIANT` branch where it exists.
    """
    prose = entry.negative_text.strip()
    branches: list[dict[str, str]] = []
    for gate in gates:
        if gate.startswith("CG-"):
            branches.append(
                {
                    "gate": gate,
                    "on": "FAIL",
                    "action": prose or f"{entry.wp_id} acceptance item unmet; re-run the package.",
                }
            )
        else:
            branches.append(
                {
                    "gate": gate,
                    "on": "RETRY_WITH_VARIANT",
                    "action": prose or f"Re-measure {gate} under a named variant.",
                }
            )
    return branches


def _downstream_for(wp_id: str, entries: list[CatalogEntry]) -> list[str]:
    """Return packages naming this one as an input.

    Derived by inverting the catalogs' input columns rather than read from a
    declaration, because no per-package downstream list exists in the corpus.
    """
    return sorted(
        other.wp_id
        for other in entries
        if other.wp_id != wp_id and re.search(rf"\b{re.escape(wp_id)}\b", other.consumes_text)
    )


def _package_axes(
    entry: CatalogEntry,
    entries: list[CatalogEntry],
    ownership: dict[str, list[dict[str, str]]],
    producers: dict[str, str],
) -> dict[str, Any]:
    """Compute the axes CI-14c requires to be identical across a package's records."""
    gates = _gates_for(entry)
    # Two independent declaration sites, merged rather than one overriding the
    # other: `06` §3.2 names an owner per symbol, and `02a` states ownership
    # inline in the contract cell. A package can appear in both, and dropping
    # either source leaves an ownership hole that reads as "unowned".
    declared = [{"glob": glob, "mode": mode} for glob, mode in entry.declared_owns()]
    merged = list(ownership.get(entry.wp_id, []))
    merged.extend(item for item in declared if item not in merged)
    axes: dict[str, Any] = {
        "owns": merged,
        "gate": gates,
        "negative_branch": _negative_branches_for(entry, gates),
        "downstream": _downstream_for(entry.wp_id, entries),
        "stale_on": [],
        "env_hash": None,
    }
    if entry.is_multi_stage:
        axes["phases"] = _phases_for(entry)
    else:
        axes["workflow"] = entry.workflows[0] if entry.workflows else "SHAPE-CF"
        axes["exec_class"] = (
            entry.exec_classes[0]
            if entry.exec_classes
            else SHAPE_TO_EXEC_CLASS.get(axes["workflow"], "AI-offline")
        )
    axes["evidence"] = _evidence_artifacts(gates)
    # A provisional gate's consumers must re-derive when the final one lands,
    # or a synthetic-load figure survives as though it were measured (CI-11c).
    if "PG-RT-001a" in gates:
        axes["stale_on"] = sorted({*axes["stale_on"], "PG-RT-001b:PASS"})
    axes["produces"] = sorted(
        contract for contract, owner in producers.items() if owner == entry.wp_id
    )
    if not axes["downstream"]:
        axes["terminal"] = True
    return axes


def _record(
    requirement: Requirement,
    assignment: Assignment,
    entry: CatalogEntry | None,
    axes: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build one registry record."""
    record: dict[str, Any] = {
        "req": requirement.req_id,
        "spec_ref": requirement.spec_ref,
        "priority": requirement.priority or "M",
        "tag": requirement.tag,
        "wp": assignment.wp,
        "artifact": [],
        "owns": [],
        "contract": {"consumes": [], "produces": []},
        "gate": [],
        "negative_branch": [],
        "downstream": [],
        "terminal": True,
        "stale_on": [],
        "env_hash": None,
    }
    if entry is not None and axes is not None:
        record.update(axes)
        record["artifact"] = list(axes.get("evidence", []))
        record.pop("evidence", None)
        # Evidence directories are created when the gate is actually measured.
        # `06` §2.2 gives `planned` for exactly this: it lets CI-06 accept a
        # declared path that does not exist yet, without weakening the rule for
        # paths that should exist and do not.
        if any(not (REPO_ROOT / item["path"]).exists() for item in record["artifact"]):
            record["planned"] = True
        record["contract"] = {
            "consumes": sorted(dict.fromkeys(CONTRACT_ID.findall(entry.consumes_text))),
            "produces": list(axes.get("produces", [])),
        }
        record.pop("produces", None)
        if record["downstream"]:
            record.pop("terminal", None)

    provenance: dict[str, Any] = {"wp_rule": assignment.rule}
    if assignment.rule in (RULE_AMBIGUOUS, RULE_COVERAGE):
        provenance["wp_candidates"] = list(assignment.candidates)
    if not requirement.tag_is_declared:
        provenance["source"] = f"tag as written: {requirement.raw_tag or '(none)'}"
    record["provenance"] = provenance
    return record


def _plan_axis_record(entry: CatalogEntry, axes: dict[str, Any], index: int) -> dict[str, Any]:
    """Build the plan-axis record for a package the requirements corpus cannot reach.

    Such a package owns the plan's own execution machinery rather than robot
    behaviour, so it has no `FR-*` to point at — the whole BOOT band, plus
    `WP-N1-04` (normalisation-hash issuance) and the environment and version-pin
    packages whose cited requirements are owned elsewhere.

    `00` §8.2a provides the `PLAN-<band>-<nn>` axis for exactly this, and
    CI-01/CI-01b exclude it from the specification comparison. Without it these
    packages cannot be registered at all: inventing an `FR-*` violates CI-01b,
    and omitting the record leaves the 177 difference non-empty. The corpus
    names only `PLAN-BOOT-*` today because BOOT was the only band anyone had
    checked; the axis generalises without changing its meaning.
    """
    record: dict[str, Any] = {
        "req": f"PLAN-{entry.band}-{index:02d}",
        "spec_ref": "00#3.5",
        "priority": "M",
        "tag": "신규구현",
        "wp": entry.wp_id,
        "artifact": [],
        "contract": {"consumes": [], "produces": []},
        "provenance": {
            "wp_rule": RULE_PLAN_AXIS,
            "source": f"{entry.source.name}:{entry.source_line}",
        },
    }
    record.update(axes)
    record["artifact"] = list(axes.get("evidence", []))
    record.pop("evidence", None)
    record.pop("produces", None)
    if any(not (REPO_ROOT / item["path"]).exists() for item in record["artifact"]):
        record["planned"] = True
    record["contract"] = {"consumes": [], "produces": sorted(axes.get("produces", []))}
    record["owns"] = [
        {"glob": glob, "mode": mode} for glob, mode in entry.declared_owns()
    ] or axes.get("owns", [])
    if not record.get("downstream"):
        record["terminal"] = True
    return record


def build(plan_dir: Path, spec_dir: Path, spine_ref: str) -> tuple[dict[str, Any], BuildReport]:
    """Seed the registry document from the corpus.

    Args:
        plan_dir: Directory holding the planning documents.
        spec_dir: Directory holding the specification documents.
        spine_ref: Canonical spine reference, `docs/plan/<file>@<commit>`.

    Returns:
        (dict) Two values: the registry document, and the build report.
    """
    registry_doc = plan_dir / "06-추적성-레지스트리.md"
    requirements = parse_spec(spec_dir)
    entries = parse_catalogs(plan_dir)
    by_id = {entry.wp_id: entry for entry in entries}
    ownership = read_glob_ownership(registry_doc)
    producers = read_contract_producers(plan_dir)

    assignments = fill_coverage(
        resolve(
            [requirement.req_id for requirement in requirements],
            entries,
            read_doc06_assignments(registry_doc),
        ),
        entries,
    )
    axes_cache = {
        entry.wp_id: _package_axes(entry, entries, ownership, producers) for entry in entries
    }

    records = [
        _record(
            requirement,
            assignments[requirement.req_id],
            by_id.get(assignments[requirement.req_id].wp),
            axes_cache.get(assignments[requirement.req_id].wp),
        )
        for requirement in requirements
    ]

    unreached = unregistered_packages(assignments, entries)
    per_band: dict[str, int] = {}
    for wp_id in unreached:
        entry = by_id[wp_id]
        per_band[entry.band] = per_band.get(entry.band, 0) + 1
        records.append(_plan_axis_record(entry, axes_cache[wp_id], per_band[entry.band]))
    records.sort(key=lambda record: record["req"])

    rules: dict[str, int] = {}
    for assignment in assignments.values():
        rules[assignment.rule] = rules.get(assignment.rule, 0) + 1

    report = BuildReport(
        requirements=len(requirements),
        packages=len(entries),
        assignment_rules=rules,
        undeclared_priority=[r.req_id for r in requirements if not r.priority_is_valid],
        undeclared_tag=[r.req_id for r in requirements if not r.tag_is_declared],
        packages_without_records=[],
        packages_without_acceptance=[
            entry.wp_id for entry in entries if entry.acceptance_item_count() == 0
        ],
        multi_stage_packages=[entry.wp_id for entry in entries if entry.is_multi_stage],
        pipe_defects=[
            f"{path.name}:{line}"
            for directory in (spec_dir, plan_dir)
            for path in sorted(directory.glob("*.md"))
            for line, _ in find_pipe_defects(path)
        ],
    )

    document = {"version": SCHEMA_VERSION, "spine_ref": spine_ref, "entries": records}
    return document, report


def unresolved_rules() -> tuple[str, ...]:
    """Return the resolution rules that leave a requirement without an owner."""
    return (RULE_AMBIGUOUS, RULE_UNCITED)


def deferred_count(document: dict[str, Any]) -> int:
    """Count records registered without an owning work package.

    Args:
        document: Registry document.

    Returns:
        (int) Records whose `wp` is `DEFERRED`.
    """
    return sum(1 for record in document["entries"] if record["wp"] == DEFERRED)
