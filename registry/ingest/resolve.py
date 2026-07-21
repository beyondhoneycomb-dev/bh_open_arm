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

import re
from dataclasses import dataclass
from pathlib import Path

from registry.ingest.catalog import WP_ID, CatalogEntry
from registry.ingest.markdown import all_tables, plain_text
from registry.ingest.spec import REQ_ID

# `06` §6 abbreviates a contiguous block of requirements as `FR-GUI-060~074`:
# the right-hand side is a bare 3-digit number inheriting the left prefix. The
# left side is matched as a bare 3-digit group rather than a whole id because
# the same column also writes `FR-GUI-003/010~025b`, where the range opens on
# an abbreviated id; anchoring on a full id would make that row invisible, and
# invisible is the one outcome this module may not produce.
_RANGE_BOUNDS = re.compile(r"(?<!\d)(\d{3})\s*~\s*([0-9A-Za-z]+)")
# The prefix a bare bound inherits is the nearest id declared to its left.
_RANGE_PREFIX = re.compile(r"\b((?:FR|NFR)-[A-Z]{2,4})-\d{3}")
_BARE_BOUND = re.compile(r"^\d{3}$")
# The widest legitimate block in the corpus is 15 (`FR-GUI-060~074`). The cap is
# not a style limit: it is what separates a block from a digit typo, which would
# otherwise expand into hundreds of fabricated assignments.
MAX_RANGE_SPAN = 50

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


def expand_req_ranges(cell: str) -> tuple[list[str], list[str]]:
    """Expand every `<prefix>-<lo>~<hi>` block in one cell into its member ids.

    A range is only recognised where a requirement prefix is declared to the
    left of it in the same cell, which is what separates an id block from
    ordinary prose — the same column writes "하네스(조건 1~7)", meaning seven
    numbered conditions and no requirement at all.

    A range that is recognised but does not parse is returned as a defect
    rather than dropped. Dropping it is indistinguishable from a document that
    never had a range, and `06` §6 is the only place the corpus states
    ownership: an id lost here falls through to the weaker sole-citation rule
    and acquires an owner the canon contradicts.

    Args:
        cell: Plain-text requirement cell.

    Returns:
        (tuple) Two values: the expanded requirement ids in ascending order,
        and one message per malformed range.
    """
    prefixes = [(found.start(), found.group(1)) for found in _RANGE_PREFIX.finditer(cell)]
    expanded: list[str] = []
    defects: list[str] = []

    for bounds in _RANGE_BOUNDS.finditer(cell):
        inherited = [name for start, name in prefixes if start < bounds.start()]
        if not inherited:
            continue
        prefix = inherited[-1]
        low, high = bounds.group(1), bounds.group(2)
        expression = f"{prefix}-{low}~{high}"

        if not _BARE_BOUND.match(high):
            defects.append(f"{expression} — right bound is not a bare 3-digit number")
            continue
        first, last = int(low), int(high)
        if last < first:
            defects.append(f"{expression} — bounds are reversed")
            continue
        if last - first + 1 > MAX_RANGE_SPAN:
            span = last - first + 1
            defects.append(f"{expression} — spans {span}, over the {MAX_RANGE_SPAN} cap")
            continue
        expanded.extend(f"{prefix}-{number:03d}" for number in range(first, last + 1))
    return expanded, defects


def read_doc06_assignments(registry_doc: Path) -> tuple[dict[str, str], list[str]]:
    """Read the explicit requirement-to-package assignments in `06` §6.

    Only rows naming exactly one package are taken. A row naming several is a
    shared responsibility, not an assignment, and treating it as one would put
    a fabricated owner into the canonical column.

    Ids written out and ids covered by a range carry the same authority, so
    both are recorded. Expansion is not filtered against the specification
    here: this function reports what `06` §6 states, and a member the
    specification never declared is simply never looked up.

    Args:
        registry_doc: Path to `06-추적성-레지스트리.md`.

    Returns:
        (tuple) Two values: requirement id to owning work-package id, and one
        message per malformed range, each prefixed with its owning package.
    """
    assignments: dict[str, str] = {}
    defects: list[str] = []
    for table in all_tables(registry_doc):
        requirement_column = table.column_index("대표 요구사항")
        package_column = table.exact_column_index("WP")
        if requirement_column is None or package_column is None:
            continue
        for row in table.rows:
            packages = WP_ID.findall(plain_text(row[package_column]))
            if len(packages) != 1:
                continue
            cell = plain_text(row[requirement_column])
            ranged, malformed = expand_req_ranges(cell)
            defects.extend(f"{packages[0]}: {message}" for message in malformed)
            for req_id in [*REQ_ID.findall(cell), *ranged]:
                assignments.setdefault(req_id, packages[0])
    return assignments, defects


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
