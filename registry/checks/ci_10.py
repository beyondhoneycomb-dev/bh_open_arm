"""CI-10 — `M-8` is sealed: banned as a gate id, permitted in the prose that bans it.

`M-8` means two incompatible things in the specification: `16` §8 calls it "Quest
tracking accuracy — closed without investigation", `15` calls it "control-loop
cycle time". Both readings are real, neither is a typo, so the id was retired
rather than reassigned; control-loop measurement is `PG-RT-001a`/`PG-RT-001b`
(`06` §2.3b), mapped to `NFR-PRF-054`.

The scope is the reason this rule needs writing carefully rather than quickly.
`06` §5 marks prose warnings, the normalization-ledger row, and the rule's own
table cell as explicit exceptions, because a global `\\bM-8\\b` sweep over
`docs/plan/**` matches roughly seventy-odd sentences whose entire purpose is to
explain the ban — the checker would fail on the text documenting it, on its first
run. So this rule reads *field values* at gate declaration sites and nothing else.
Text that explains why `M-8` is not a gate is the ban's justification, not its
target.
"""

from __future__ import annotations

import re

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-10"
TITLE = "M-8 sealed"

SEALED_GATE_ID = re.compile(r"^M-8$")

REPLACEMENT_GATES = "PG-RT-001a / PG-RT-001b"


def run(corpus: Corpus) -> RuleResult:
    """Report `M-8` occupying a gate declaration site.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per sealed id used as a gate value.
    """
    sites = corpus.gate_declaration_sites

    findings = [
        fail(
            rule_id=RULE_ID,
            req_or_wp=cell.owner,
            path=cell.location(),
            reason=(
                f"sealed id M-8 is used as a gate value at a {cell.site}; the id carries two "
                "conflicting meanings in the specification and was retired, not reassigned"
            ),
            expected=REPLACEMENT_GATES,
            actual=cell.value,
        )
        for cell in sites
        if SEALED_GATE_ID.match(cell.value.strip())
    ]

    return RuleResult(
        rule_id=RULE_ID, findings=tuple(findings), sites=len(sites), vacuous=not sites
    )
