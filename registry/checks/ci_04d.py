"""CI-04d — `OUT` reason must exist: dropping a requirement needs a cited decision.

`06` §5 replaced a phantom `CG-OUT-01` acceptance gate with this rule. `OUT` is not
work, so it has no acceptance check; what it must have is an `out_reason` pointing
at a `U-*` decision or at the specification location where the requirement was
struck through or demoted. Without that citation, "we are not doing this" carries
no record of who decided it.
"""

from __future__ import annotations

import re

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-04d"
TITLE = "OUT reason exists"

WP_OUT = "OUT"

# A `U-*` user decision, or a citation of a struck-through / demoted spec location.
DECISION_REFERENCE = re.compile(r"\bU-\d+\b|~~|폐기|격하|\b\d{2}\s*§")


def run(corpus: Corpus) -> RuleResult:
    """Report `OUT` records whose `out_reason` cites no decision or spec location.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per uncited `OUT` record.
    """
    out_records = [record for record in corpus.entries if record.get("wp") == WP_OUT]

    findings = []
    for record in out_records:
        reason = str(record.get("out_reason", "") or "").strip()
        if reason and DECISION_REFERENCE.search(reason):
            continue
        findings.append(
            fail(
                rule_id=RULE_ID,
                req_or_wp=str(record.get("req", "?")),
                path=corpus.rel(corpus.registry_path),
                reason=(
                    "record is marked OUT but out_reason cites no U-* decision and no "
                    "specification location where the requirement was dropped or demoted"
                ),
                expected="out_reason referencing a U-* decision or a struck-through spec location",
                actual=reason or "(out_reason absent or empty)",
            )
        )

    return RuleResult(
        rule_id=RULE_ID,
        findings=tuple(findings),
        sites=len(out_records),
        vacuous=not out_records,
        notes=(
            ("no record carries wp: OUT, so this rule examined nothing on this corpus.",)
            if not out_records
            else ()
        ),
    )
