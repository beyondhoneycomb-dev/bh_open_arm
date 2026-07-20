"""CI-12 — target coverage: a per-target gate must render a verdict per target.

`PG-IK-001` is judged per deployment target, so a package carrying it needs a
verdict for all four targets of `00` §2.1 P-2. This is an enumerable predicate,
not a judgement call: the target set is closed, and a missing entry means one
deployment target's support status was never established either way.
"""

from __future__ import annotations

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail
from registry.checks.wp import DEPLOY_TARGETS, PER_TARGET_GATES

RULE_ID = "CI-12"
TITLE = "target coverage"


def run(corpus: Corpus) -> RuleResult:
    """Report packages with a per-target gate but incomplete target coverage.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per package with missing target verdicts.
    """
    findings = []
    sites = 0

    for wp_id, records in sorted(corpus.by_wp.items()):
        gates = {str(g) for record in records for g in record.get("gate", []) or []}
        triggering = gates & PER_TARGET_GATES
        if not triggering:
            continue
        sites += 1
        declared = {str(t) for record in records for t in record.get("targets", []) or []}
        missing = DEPLOY_TARGETS - declared
        unknown = declared - DEPLOY_TARGETS
        if not missing and not unknown:
            continue
        problems = []
        if missing:
            problems.append(f"missing {', '.join(sorted(missing))}")
        if unknown:
            problems.append(f"unknown {', '.join(sorted(unknown))}")
        findings.append(
            fail(
                rule_id=RULE_ID,
                req_or_wp=wp_id,
                path=corpus.rel(corpus.registry_path),
                reason=(
                    f"package carries the per-target gate {', '.join(sorted(triggering))} but "
                    "does not render a verdict for every deployment target"
                ),
                expected=", ".join(sorted(DEPLOY_TARGETS)),
                actual="; ".join(problems),
            )
        )

    return RuleResult(rule_id=RULE_ID, findings=tuple(findings), sites=sites, vacuous=not sites)
