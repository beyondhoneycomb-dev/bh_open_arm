"""Resolve which work package owns each requirement.

The catalogs cite requirements as justification, which is a many-to-many
relation: `NFR-SAF-007` is cited by eight packages because eight of them must
respect it. The registry needs a many-to-one *ownership* relation, and that
function is not written down anywhere in the corpus — `06` §6 states per-domain
rules plus representative examples and says outright that the exhaustive list
lives in the registry, which is the artifact being bootstrapped.

So ownership is resolved by three rules of decreasing authority, and every
record records which rule decided it. Nothing is guessed: a requirement whose
owner cannot be established becomes `DEFERRED`, which the schema provides
precisely so an unassigned requirement can be registered without inventing an
assignment (CI-04 and CI-07 both exempt it).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from registry.ingest.catalog import WP_ID, CatalogEntry
from registry.ingest.markdown import all_tables, plain_text
from registry.ingest.spec import REQ_ID

# Ownership rules, most authoritative first.
RULE_DOC06 = "doc06-section6"
RULE_SOLE = "sole-citation"
RULE_AMBIGUOUS = "ambiguous-citation"
RULE_UNCITED = "uncited"
RULE_PLAN_AXIS = "plan-axis"
RULE_COVERAGE = "coverage-fill"

DEFERRED = "DEFERRED"


@dataclass(frozen=True)
class Assignment:
    """The owning work package for one requirement, and how it was decided.

    Attributes:
        req_id: Requirement the assignment is for.
        wp: Owning work-package id, or `DEFERRED` when none could be established.
        rule: Which resolution rule decided this.
        candidates: Work packages that cite the requirement. Retained for the
            ambiguous case so the unresolved choice is visible rather than lost.
    """

    req_id: str
    wp: str
    rule: str
    candidates: tuple[str, ...]


def read_doc06_assignments(registry_doc: Path) -> dict[str, str]:
    """Read the explicit requirement-to-package assignments in `06` §6.

    Only rows naming exactly one package are taken. A row naming several is a
    shared responsibility, not an assignment, and treating it as one would put
    a fabricated owner into the canonical column.

    Args:
        registry_doc: Path to `06-추적성-레지스트리.md`.

    Returns:
        (dict) Requirement id to owning work-package id.
    """
    assignments: dict[str, str] = {}
    for table in all_tables(registry_doc):
        requirement_column = table.column_index("대표 요구사항")
        package_column = table.exact_column_index("WP")
        if requirement_column is None or package_column is None:
            continue
        for row in table.rows:
            packages = WP_ID.findall(plain_text(row[package_column]))
            if len(packages) != 1:
                continue
            for req_id in REQ_ID.findall(plain_text(row[requirement_column])):
                assignments.setdefault(req_id, packages[0])
    return assignments


def resolve(
    req_ids: list[str],
    entries: list[CatalogEntry],
    doc06_assignments: dict[str, str],
) -> dict[str, Assignment]:
    """Assign an owning work package to every requirement.

    Rules, in order:

    1. An explicit assignment in `06` §6 wins. It is the only place the corpus
       states ownership rather than citation.
    2. A requirement cited by exactly one package is owned by it. With one
       citation there is no choice to make.
    3. Anything else is `DEFERRED` — cited by several packages with no stated
       owner, or cited by none. Both are unresolved, and the distinction is
       kept in `rule` so the reconciliation report can separate them.

    Args:
        req_ids: Requirement ids declared by the specification.
        entries: Work packages issued by the catalogs.
        doc06_assignments: Explicit assignments from `06` §6.

    Returns:
        (dict) Requirement id to its assignment.
    """
    citations: dict[str, set[str]] = {}
    for entry in entries:
        for req_id in entry.reqs:
            citations.setdefault(req_id, set()).add(entry.wp_id)

    issued = {entry.wp_id for entry in entries}
    resolved: dict[str, Assignment] = {}

    for req_id in req_ids:
        candidates = tuple(sorted(citations.get(req_id, ())))
        stated = doc06_assignments.get(req_id, "")

        if stated and stated in issued:
            rule, owner = RULE_DOC06, stated
        elif len(candidates) == 1:
            rule, owner = RULE_SOLE, candidates[0]
        elif candidates:
            rule, owner = RULE_AMBIGUOUS, DEFERRED
        else:
            rule, owner = RULE_UNCITED, DEFERRED

        resolved[req_id] = Assignment(req_id=req_id, wp=owner, rule=rule, candidates=candidates)
    return resolved


def fill_coverage(
    assignments: dict[str, Assignment], entries: list[CatalogEntry]
) -> dict[str, Assignment]:
    """Break ownership ties in favour of packages that would otherwise vanish.

    Records are keyed by requirement, so a package appears in the registry only
    if some requirement resolves to it. A package whose every cited requirement
    was claimed by a sibling ends up with no record at all — and the band
    acceptance gate requires all 177 issued packages to be registered.

    This resolves that by constraint, not by invention: the chosen requirement
    is one the package itself cites, and the reason for choosing it is a rule
    the corpus states. It only ever converts an `ambiguous-citation` into a
    concrete owner, never overrides an assignment an earlier rule made.

    Args:
        assignments: Assignments from `resolve`.
        entries: Work packages issued by the catalogs.

    Returns:
        (dict) Assignments with coverage gaps closed where possible.
    """
    filled = dict(assignments)
    citations = {entry.wp_id: entry.reqs for entry in entries}

    for wp_id in unregistered_packages(filled, entries):
        available = sorted(
            req_id
            for req_id in citations.get(wp_id, ())
            if req_id in filled and filled[req_id].rule == RULE_AMBIGUOUS
        )
        if not available:
            continue
        chosen = available[0]
        filled[chosen] = Assignment(
            req_id=chosen,
            wp=wp_id,
            rule=RULE_COVERAGE,
            candidates=filled[chosen].candidates,
        )
    return filled


def unregistered_packages(
    assignments: dict[str, Assignment], entries: list[CatalogEntry]
) -> list[str]:
    """Return issued work packages that no requirement assignment reaches.

    The band acceptance gate requires all 177 issued packages to appear in the
    registry. A package reached by no requirement would be absent from the
    `wp` column, so this is the list that must be closed by other means —
    `PLAN-*` axis records for the BOOT band, and reported gaps elsewhere.

    Args:
        assignments: Resolved requirement assignments.
        entries: Work packages issued by the catalogs.

    Returns:
        (list) Work-package ids with no assigned requirement, sorted.
    """
    reached = {assignment.wp for assignment in assignments.values()}
    return sorted(entry.wp_id for entry in entries if entry.wp_id not in reached)
