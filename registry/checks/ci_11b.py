"""CI-11b — undivided `PG-RT-001`: the unsplit id is not a gate.

`06` §2.3b split the control-loop gate to break a DAG deadlock: `a` runs in Wave 1
against a synthetic GIL load and is provisional, `b` runs in Wave 3C against real
cameras and real writes and is final. The undivided `PG-RT-001` does not exist in
`03`, so a field holding it names no gate at all.

Scope is identical in shape to CI-10 and for the same reason. `06` §5 limits the
ban to three places where a gate id arrives as a *value*: the ID cell of the `03`
gate table, a manifest's `gates:`/`exit_gates:`/`requires_gates:` field, and this
registry's gate axis. Prose narration, family references, the abbreviation table,
notices like this one, ledger rows, and the descriptive column of an acceptance
gate are named exceptions — `00` and `04` legitimately write the bare id in dozens
of sentences ("control-loop measurement must be PG-RT-001", "not `16`'s M-8"), and
a `docs/plan/**` regex detonates on every one of them. The seal's justification is
not the seal's target.
"""

from __future__ import annotations

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-11b"
TITLE = "undivided PG-RT-001"

UNDIVIDED_GATE = "PG-RT-001"

SPLIT_GATES = "PG-RT-001a (Wave 1, synthetic load, provisional) / PG-RT-001b (Wave 3C, final)"


def run(corpus: Corpus) -> RuleResult:
    """Report the undivided `PG-RT-001` occupying a gate declaration site.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per undivided id used as a gate value.
    """
    sites = corpus.gate_declaration_sites

    findings = [
        fail(
            rule_id=RULE_ID,
            req_or_wp=cell.owner,
            path=cell.location(),
            reason=(
                f"undivided PG-RT-001 is used as a gate value at a {cell.site}; the gate was "
                "split in 06 §2.3b and the unsplit id does not exist in 03"
            ),
            expected=SPLIT_GATES,
            actual=cell.value,
        )
        for cell in sites
        if cell.value.strip() == UNDIVIDED_GATE
    ]

    return RuleResult(
        rule_id=RULE_ID, findings=tuple(findings), sites=len(sites), vacuous=not sites
    )
