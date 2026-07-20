"""CI-01b — phantom requirement: a registry `req` the specification never declared.

This is the rule that stops the plan inventing requirement ids. `06` §5 excludes
the `PLAN-*` axis by name: those ids are grounded in plan canon rather than in
`docs/spec/`, and CI-17 verifies their `spec_ref` points at a real plan section.
"""

from __future__ import annotations

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-01b"
TITLE = "phantom requirement"

PLAN_AXIS_PREFIX = "PLAN-"


def run(corpus: Corpus) -> RuleResult:
    """Report registry requirement ids absent from the specification.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per invented requirement id.
    """
    declared = corpus.spec_requirements
    findings = []
    checked = 0
    for entry in corpus.entries:
        req = str(entry["req"])
        if req.startswith(PLAN_AXIS_PREFIX):
            continue
        checked += 1
        if req in declared:
            continue
        findings.append(
            fail(
                rule_id=RULE_ID,
                req_or_wp=req,
                path=corpus.rel(corpus.registry_path),
                reason=(
                    "registry declares a requirement id that no specification table "
                    "declares; the plan may register spec ids, never invent them"
                ),
                expected=f"{req} declared in a docs/spec requirement table",
                actual="absent from every specification requirement table",
            )
        )
    return RuleResult(rule_id=RULE_ID, findings=tuple(findings), sites=checked, vacuous=not checked)
