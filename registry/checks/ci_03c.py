"""CI-03c — contract namespace closure: no contract outside the canonical thirteen.

`06` §4.1b records the failure this prevents. A previous round of the registry
invented `CT-SCHEDULER-MAILBOX`, `CT-RT-BUDGET` and `CT-POLICY-COMPAT`; none
existed in `01` §6.2. A contract is a mutex between parallel workflows, so a
measurement's output, a copy of an upstream fact, or one package's internal
product is an artifact and is joined through `artifact[]`/`downstream[]` instead.
"""

from __future__ import annotations

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail
from registry.checks.wp import CONTRACT_ID, CONTRACT_NAMESPACE

RULE_ID = "CI-03c"
TITLE = "contract namespace closure"


def run(corpus: Corpus) -> RuleResult:
    """Report contract ids outside the thirteen-contract namespace.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per invented or malformed contract id.
    """
    findings = []
    checked = 0
    reported: set[tuple[str, str]] = set()

    for record in corpus.entries:
        contract = record.get("contract", {}) or {}
        owner = str(record.get("wp", "?"))
        for axis in ("consumes", "produces"):
            for raw in contract.get(axis, []) or []:
                contract_id = str(raw)
                checked += 1
                if not CONTRACT_ID.match(contract_id):
                    key = (contract_id, "form")
                    if key not in reported:
                        reported.add(key)
                        findings.append(
                            fail(
                                rule_id=RULE_ID,
                                req_or_wp=owner,
                                path=corpus.rel(corpus.registry_path),
                                reason=(
                                    f"contract.{axis}[] holds an id that is not of the form "
                                    "CTR-<NAME>@v<n>"
                                ),
                                expected="CTR-<NAME>@v<n>",
                                actual=contract_id,
                            )
                        )
                    continue
                name = contract_id.split("@", 1)[0]
                if name in CONTRACT_NAMESPACE:
                    continue
                key = (contract_id, "namespace")
                if key in reported:
                    continue
                reported.add(key)
                findings.append(
                    fail(
                        rule_id=RULE_ID,
                        req_or_wp=owner,
                        path=corpus.rel(corpus.registry_path),
                        reason=(
                            f"contract.{axis}[] names a contract outside the 13 declared in "
                            "01 §6.2; anything else is an artifact, not a contract"
                        ),
                        expected=f"one of {', '.join(sorted(CONTRACT_NAMESPACE))}",
                        actual=name,
                    )
                )

    return RuleResult(rule_id=RULE_ID, findings=tuple(findings), sites=checked, vacuous=not checked)
