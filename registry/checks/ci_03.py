"""CI-03 — contract producer uniqueness: exactly one producer per contract version.

A contract is a mutex between two parallel workflows (`01` §6.1). Two producers
means two definitions of the same version and no answer to "which one did I build
against"; zero producers means a consumer is reading a contract nobody owns.
`06` §5 states the failure condition as a count `≠ 1`, so both directions fail.
"""

from __future__ import annotations

from collections import defaultdict

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-03"
TITLE = "contract producer uniqueness"


def run(corpus: Corpus) -> RuleResult:
    """Report contract versions whose producer count is not exactly one.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per contract version with a bad producer count.
    """
    producers: dict[str, set[str]] = defaultdict(set)
    referenced: set[str] = set()

    for record in corpus.entries:
        contract = record.get("contract", {}) or {}
        wp_id = str(record.get("wp", ""))
        for contract_id in contract.get("produces", []) or []:
            referenced.add(str(contract_id))
            producers[str(contract_id)].add(wp_id)
        for contract_id in contract.get("consumes", []) or []:
            referenced.add(str(contract_id))

    findings = []
    for contract_id in sorted(referenced):
        owners = producers.get(contract_id, set())
        if len(owners) == 1:
            continue
        owner_list = ", ".join(sorted(owners)) if owners else "none"
        findings.append(
            fail(
                rule_id=RULE_ID,
                req_or_wp=contract_id,
                path=corpus.rel(corpus.registry_path),
                reason=(
                    "contract version has no single producing work package; a consumer "
                    "cannot say which definition it was built against"
                ),
                expected="exactly 1 work package declaring this id in contract.produces[]",
                actual=f"{len(owners)} producer(s): {owner_list}",
            )
        )

    return RuleResult(
        rule_id=RULE_ID,
        findings=tuple(findings),
        sites=len(referenced),
        vacuous=not referenced,
    )
