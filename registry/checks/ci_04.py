"""CI-04 — gateless work package: a real package with an empty `gate[]`.

The exemption matters more than the rule. `06` §5 exempts `wp ∈ {OUT, DEFERRED}`
because neither is work: `OUT` is verified by the `out_reason` rule (CI-04d), and
`DEFERRED` has nothing to accept yet. The registry currently holds hundreds of
`DEFERRED` records, so a version of this rule that forgets the exemption reports
its false failures by the hundred and buries the handful of real ones.

`06` §2.4a derives one `CG-*` per catalogue acceptance item, so any package with
at least one acceptance item automatically has a non-empty `gate[]`; an empty one
means the catalogue row enumerated no acceptance items at all.
"""

from __future__ import annotations

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-04"
TITLE = "gateless work package"


def run(corpus: Corpus) -> RuleResult:
    """Report work-package records that declare no gate.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per gateless record.
    """
    findings = [
        fail(
            rule_id=RULE_ID,
            req_or_wp=f"{record.get('req', '?')}/{record.get('wp', '?')}",
            path=corpus.rel(corpus.registry_path),
            reason=(
                "work-package record declares an empty gate[]; a package with any "
                "acceptance item derives at least one CG-* (06 §2.4a)"
            ),
            expected="gate[] length >= 1",
            actual="gate[] is empty",
        )
        for record in corpus.work_entries
        if not record.get("gate")
    ]

    return RuleResult(
        rule_id=RULE_ID,
        findings=tuple(findings),
        sites=len(corpus.work_entries),
        vacuous=not corpus.work_entries,
    )
