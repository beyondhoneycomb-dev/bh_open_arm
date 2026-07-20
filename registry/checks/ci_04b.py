"""CI-04b — `CG-*` without evidence: an acceptance check nothing can be shown for.

This rule is the sole offset for allowing `CG-*` at all. `06` §2.3 concedes that a
package defining its own acceptance check makes judge and player the same person,
and the only thing standing against a loosely written check is the requirement
that it name an observable produced artifact. A `CG-*` with no evidence artifact
is an assertion that cannot be inspected, so it is rejected.

Findings are reported once per distinct `CG-*`, not once per record: records are
keyed by requirement, so one acceptance check appears in many of them, and a
per-record report would inflate a single defect into dozens.
"""

from __future__ import annotations

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-04b"
TITLE = "CG-* without evidence"


def run(corpus: Corpus) -> RuleResult:
    """Report acceptance checks with no evidence artifact declared.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per acceptance check lacking evidence.
    """
    evidence_by_wp: dict[str, set[str]] = {}
    gates_by_wp: dict[str, set[str]] = {}

    for wp_id, records in corpus.by_wp.items():
        evidence: set[str] = set()
        gates: set[str] = set()
        for record in records:
            for artifact in record.get("artifact", []) or []:
                path = str(artifact.get("path", "")).strip()
                if path:
                    evidence.add(path)
            gates.update(g for g in record.get("gate", []) or [] if str(g).startswith("CG-"))
        evidence_by_wp[wp_id] = evidence
        gates_by_wp[wp_id] = gates

    findings = []
    sites = 0
    for wp_id in sorted(gates_by_wp):
        for gate in sorted(gates_by_wp[wp_id]):
            sites += 1
            if evidence_by_wp[wp_id]:
                continue
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=f"{wp_id}/{gate}",
                    path=corpus.rel(corpus.registry_path),
                    reason=(
                        "acceptance check references no evidence artifact path; a CG-* that "
                        "names no observable output cannot be inspected"
                    ),
                    expected="at least one artifact[].path on the owning work package",
                    actual="artifact[] is empty for this work package",
                )
            )

    return RuleResult(rule_id=RULE_ID, findings=tuple(findings), sites=sites, vacuous=not sites)
