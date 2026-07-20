"""CI-01 — missing mapping: a declared requirement that no record implements.

Scope note, and it is the whole difficulty of this rule. `06` §5 states the check
as the regex `(FR|NFR)-[A-Z]{3}-\\d{3}` swept over `docs/spec/`. Run literally,
that regex harvests ids that appear only in prose *about* the id format — the
naming counter-examples in `docs/spec/00` §5.1 such as `FR-NFR-001` are the
clearest case — and none of those requirements exist. Treating them as the
requirement universe would demand registry records for requirements nobody wrote.

So the implementable universe is the set declared in the specification's
requirement tables, via `registry.ingest.spec`. The literal regex is still
evaluated, and the difference between the two sets is reported as a note. That
difference is evidence about the rule's wording, not about the corpus, so it does
not fail the build — but it is not swallowed either.
"""

from __future__ import annotations

import re

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-01"
TITLE = "missing mapping"

PLAN_AXIS_PREFIX = "PLAN-"

# The wording of `06` §5, preserved so the gap between rule and implementation
# stays measurable instead of becoming folklore.
LITERAL_RULE_PATTERN = re.compile(r"(FR|NFR)-[A-Z]{3}-\d{3}")


def _literal_sweep(corpus: Corpus) -> frozenset[str]:
    """Apply the literal `06` §5 regex to the specification directory.

    Args:
        corpus: The corpus under test.

    Returns:
        (frozenset[str]) Every id the literal regex matches.
    """
    found: set[str] = set()
    for path in sorted(corpus.spec_dir.glob("*.md")):
        found.update(
            match.group(0)
            for match in LITERAL_RULE_PATTERN.finditer(path.read_text(encoding="utf-8"))
        )
    return frozenset(found)


def run(corpus: Corpus) -> RuleResult:
    """Report specification requirements that no registry record maps.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) Findings for unmapped requirements, plus the wording note.
    """
    declared = corpus.spec_requirements
    # `06` §2.2: the PLAN-* axis is grounded in plan canon, not the spec, so it is
    # out of scope here and CI-17 verifies its `spec_ref` instead.
    mapped = {
        str(entry["req"])
        for entry in corpus.entries
        if not str(entry["req"]).startswith(PLAN_AXIS_PREFIX)
    }
    unmapped = sorted(declared - mapped)

    findings = tuple(
        fail(
            rule_id=RULE_ID,
            req_or_wp=req,
            path=corpus.rel(corpus.spec_dir),
            reason=(
                "requirement is declared in a specification table but no registry record maps it"
            ),
            expected="one registry record whose `req` equals this id",
            actual="no matching record in registry/traceability.yaml",
        )
        for req in unmapped
    )

    literal = _literal_sweep(corpus)
    prose_only = sorted(literal - declared)
    notes = (
        f"rule wording vs implementable form: the literal `06` §5 regex matches "
        f"{len(literal)} ids over docs/spec/, the declaration tables declare "
        f"{len(declared)}. The {len(prose_only)} extra ids occur only in prose about "
        f"the id format (e.g. {', '.join(prose_only[:3])}) and are not requirements; "
        f"judging against them would demand records for requirements nobody wrote.",
    )

    return RuleResult(
        rule_id=RULE_ID,
        findings=findings,
        sites=len(declared),
        vacuous=not declared,
        notes=notes,
    )
