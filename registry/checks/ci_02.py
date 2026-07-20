"""CI-02 — duplicate ownership: two work packages holding one path at one time.

`06` §3.2 is explicit that sequential handover is not a violation: `WP-1-02` →
`WP-1-03` share `openarm_follower_oa.py` because one hands it to the other, and
`WP-0A-01` → `WP-1-03` share `backend/actuation/**` for the same reason. The
handover relation is declared in the 소유 WP column of that section's table, and
this rule reads it from there rather than hard-coding pairs, so that adding a
handover to the document is enough to keep the build honest.

Multi-stage packages expand `phases[].owns` as well, since a stage can claim a
path the package-level union does not spell out.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from typing import Any

from registry.checks.corpus import Corpus
from registry.checks.globs import expand, split_globs
from registry.checks.model import RuleResult, fail
from registry.ingest.catalog import WP_ID
from registry.ingest.markdown import all_tables, plain_text

RULE_ID = "CI-02"
TITLE = "duplicate ownership"

MODE_EXCLUSIVE = "EXCLUSIVE"

OWNERSHIP_DOC = "06-추적성-레지스트리.md"


def handover_chains(corpus: Corpus) -> frozenset[frozenset[str]]:
    """Read the sequential-handover relations declared in `06` §3.2.

    A row whose owner cell names more than one work package is a handover chain:
    the packages hold the symbol one after another, never at once.

    Args:
        corpus: The corpus under test.

    Returns:
        (frozenset[frozenset[str]]) Each set is one handover chain.
    """
    path = corpus.plan_dir / OWNERSHIP_DOC
    if not path.is_file():
        return frozenset()
    chains: set[frozenset[str]] = set()
    for table in all_tables(path):
        owner_column = table.exact_column_index("소유 WP")
        if owner_column is None:
            continue
        for row in table.rows:
            if owner_column >= len(row):
                continue
            packages = frozenset(WP_ID.findall(plain_text(row[owner_column])))
            if len(packages) > 1:
                chains.add(packages)
    return frozenset(chains)


def _exclusive_claims(corpus: Corpus) -> dict[str, set[str]]:
    """Collect every `EXCLUSIVE` glob claimed by each work package.

    Args:
        corpus: The corpus under test.

    Returns:
        (dict[str, set[str]]) `WP-*` to the globs it exclusively claims.
    """
    claims: dict[str, set[str]] = defaultdict(set)
    for wp_id, records in corpus.by_wp.items():
        for record in records:
            for owned in _all_owns(record):
                if owned.get("mode") != MODE_EXCLUSIVE:
                    continue
                claims[wp_id].update(split_globs(str(owned.get("glob", ""))))
    return claims


def _all_owns(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Return package-level and stage-level ownership declarations of a record.

    Args:
        record: A registry record.

    Returns:
        (list[dict[str, Any]]) Ownership entries from `owns[]` and `phases[].owns`.
    """
    owned = list(record.get("owns", []) or [])
    for phase in record.get("phases", []) or []:
        owned.extend(phase.get("owns", []) or [])
    return owned


def run(corpus: Corpus) -> RuleResult:
    """Report real files exclusively owned by two packages at the same time.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per unsanctioned overlapping pair.
    """
    claims = _exclusive_claims(corpus)
    chains = handover_chains(corpus)
    files = corpus.tracked_files

    expanded = {wp: expand(tuple(sorted(globs)), files) for wp, globs in claims.items()}

    findings = []
    for left, right in combinations(sorted(expanded), 2):
        overlap = expanded[left] & expanded[right]
        if not overlap:
            continue
        if any({left, right} <= chain for chain in chains):
            continue
        findings.append(
            fail(
                rule_id=RULE_ID,
                req_or_wp=f"{left}+{right}",
                path=", ".join(sorted(overlap)[:4]),
                reason=(
                    "two work packages hold EXCLUSIVE ownership of the same real file "
                    "with no sequential handover declared in 06 §3.2"
                ),
                expected="exactly one owning work package per path at a time",
                actual=f"{len(overlap)} shared path(s) between {left} and {right}",
            )
        )

    return RuleResult(
        rule_id=RULE_ID,
        findings=tuple(findings),
        sites=sum(len(paths) for paths in expanded.values()),
        vacuous=not any(expanded.values()),
    )
