"""CI-08 — contract version pinning: no range operators in `consumes[]`.

`06` §4.2 requires a consumer to name the exact frozen generation it was built
against. A range operator reintroduces the question the `@v<n>` scheme exists to
answer — "which schema was this compiled against" — and answers it differently
depending on when the build ran.
"""

from __future__ import annotations

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-08"
TITLE = "contract version pinning"

# `06` §4.2 names these four by symbol.
FLOATING_OPERATORS = ("^", "~", "latest", "*")


def run(corpus: Corpus) -> RuleResult:
    """Report `consumes[]` entries carrying a floating version operator.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per unpinned contract reference.
    """
    findings = []
    sites = 0
    reported: set[tuple[str, str]] = set()

    for record in corpus.entries:
        owner = str(record.get("wp", "?"))
        for raw in (record.get("contract", {}) or {}).get("consumes", []) or []:
            contract_id = str(raw)
            sites += 1
            found = [op for op in FLOATING_OPERATORS if op in contract_id]
            if not found:
                continue
            key = (owner, contract_id)
            if key in reported:
                continue
            reported.add(key)
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=owner,
                    path=corpus.rel(corpus.registry_path),
                    reason=(
                        "contract.consumes[] uses a floating version operator, so which frozen "
                        "generation this was built against depends on when the build ran"
                    ),
                    expected="an exact CTR-<NAME>@v<n> pin",
                    actual=f"{contract_id} (contains {', '.join(found)})",
                )
            )

    return RuleResult(rule_id=RULE_ID, findings=tuple(findings), sites=sites, vacuous=not sites)
