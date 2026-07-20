"""CI-05e — no state machine on `CG-*`: acceptance checks are `PASS`/`FAIL` binary.

`00` §8.0a is canon and `06` §2.3 defers to it. The five-state machine belongs to
`PG-*` alone, and each forbidden state breaks something specific when attached to
an acceptance check:

* `DEGRADED_ACCEPTED` — the package defined this check itself, so judge and player
  are the same person; it lets a package lower its own acceptance line and declare
  itself through. This is the dangerous one.
* `FAIL_BLOCKING` — descendant invalidation looks like it will fire and does not.
  `gate_index` builds its reverse index from `PG-*` only, so a `CG-*` has no
  descendant set. Believing otherwise is the actual hazard.
* `RETRY_WITH_VARIANT` / `SUPERSEDED` — re-running is what a `CG-*` does by default
  when it is not finished; naming it a state confuses it with `PG-*` variant
  re-measurement, which carries named-variant and contract-unchanged conditions.
"""

from __future__ import annotations

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail
from registry.checks.wp import CG_FORBIDDEN_STATES

RULE_ID = "CI-05e"
TITLE = "no state machine on CG-*"


def run(corpus: Corpus) -> RuleResult:
    """Report acceptance checks carrying a `PG-*` state machine value.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per forbidden state on a `CG-*`.
    """
    findings = []
    sites = 0
    reported: set[tuple[str, str, str]] = set()

    for record in corpus.entries:
        owner = str(record.get("wp", "?"))
        declared = {str(g) for g in record.get("gate", []) or []}
        for branch in record.get("negative_branch", []) or []:
            gate = str(branch.get("gate", ""))
            if not gate.startswith("CG-") or gate not in declared:
                continue
            sites += 1
            state = str(branch.get("on", ""))
            if state not in CG_FORBIDDEN_STATES:
                continue
            key = (owner, gate, state)
            if key in reported:
                continue
            reported.add(key)
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=f"{owner}/{gate}",
                    path=corpus.rel(corpus.registry_path),
                    reason=(
                        "acceptance check declares a PG-* state machine value; CG-* is "
                        "PASS/FAIL binary per 00 §8.0a and has no descendant set"
                    ),
                    expected="on: FAIL",
                    actual=f"on: {state}",
                )
            )

    return RuleResult(rule_id=RULE_ID, findings=tuple(findings), sites=sites, vacuous=not sites)
