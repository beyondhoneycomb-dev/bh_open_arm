"""CI-05c — state coverage: a `PG-*` gate must design at least one failure state.

Applies to `PG-*` elements only. `06` §2.3 spells out why: `CG-*` is `PASS`/`FAIL`
binary, so demanding a five-state branch from it would be demanding the very thing
CI-05e forbids. A `PG-*` that declares only `PASS` and `SUPERSEDED` has no designed
failure path — the measurement is allowed to fail and nothing says what follows.
"""

from __future__ import annotations

from collections import defaultdict

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail
from registry.checks.wp import PG_FAILURE_STATES

RULE_ID = "CI-05c"
TITLE = "state coverage"


def run(corpus: Corpus) -> RuleResult:
    """Report `PG-*` gates with no failure state among their negative branches.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per gate lacking a designed failure path.
    """
    states: dict[tuple[str, str], set[str]] = defaultdict(set)

    for record in corpus.entries:
        owner = str(record.get("wp", "?"))
        declared = {str(g) for g in record.get("gate", []) or []}
        for branch in record.get("negative_branch", []) or []:
            gate = str(branch.get("gate", ""))
            if gate.startswith("PG-") and gate in declared:
                states[(owner, gate)].add(str(branch.get("on", "")))

    findings = [
        fail(
            rule_id=RULE_ID,
            req_or_wp=f"{owner}/{gate}",
            path=corpus.rel(corpus.registry_path),
            reason=(
                "measurement gate declares no failure state, so the plan has not decided "
                "what happens when the measurement fails"
            ),
            expected=f"at least one of {', '.join(sorted(PG_FAILURE_STATES))}",
            actual=", ".join(sorted(declared)) or "(no negative_branch state)",
        )
        for (owner, gate), declared in sorted(states.items())
        if not declared & PG_FAILURE_STATES
    ]

    return RuleResult(
        rule_id=RULE_ID, findings=tuple(findings), sites=len(states), vacuous=not states
    )
