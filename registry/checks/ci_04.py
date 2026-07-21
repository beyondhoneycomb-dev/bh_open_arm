"""CI-04 — gateless work package: a real package with an empty `gate[]`.

The exemption matters more than the rule. `06` §5 exempts `wp ∈ {OUT, DEFERRED}`
because neither is work: `OUT` is verified by the `out_reason` rule (CI-04d), and
`DEFERRED` has nothing to accept yet. The registry currently holds hundreds of
`DEFERRED` records, so a version of this rule that forgets the exemption reports
its false failures by the hundred and buries the handful of real ones.

`06` §2.4a derives one `CG-*` per catalogue acceptance item, so the presence this
rule requires is a derived `CG-*`, not a non-empty `gate[]`. Those were the same
test only while `gate[]` held nothing but `CG-*`; once measurement gates (`PG-*`)
are also bound into `gate[]`, a package can carry a `PG-*` and still enumerate no
acceptance items — the exact defect this rule exists to catch. So the predicate
counts `CG-*` derivations, and a `PG-*` does not satisfy it.
"""

from __future__ import annotations

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-04"
TITLE = "gateless work package"

CG_PREFIX = "CG-"


def run(corpus: Corpus) -> RuleResult:
    """Report work-package records that derive no acceptance check.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per record with no `CG-*` in its gate axis.
    """
    findings = [
        fail(
            rule_id=RULE_ID,
            req_or_wp=f"{record.get('req', '?')}/{record.get('wp', '?')}",
            path=corpus.rel(corpus.registry_path),
            reason=(
                "work-package record derives no CG-* acceptance check; a package with any "
                "acceptance item derives at least one CG-* (06 §2.4a). A bound PG-* "
                "measurement gate does not substitute for an acceptance item"
            ),
            expected="at least one CG-* in gate[]",
            actual=f"gate[] = {record.get('gate') or '[]'} (no CG-*)",
        )
        for record in corpus.work_entries
        if not any(str(gate).startswith(CG_PREFIX) for gate in record.get("gate", []) or [])
    ]

    return RuleResult(
        rule_id=RULE_ID,
        findings=tuple(findings),
        sites=len(corpus.work_entries),
        vacuous=not corpus.work_entries,
    )
