"""CI-03d — primitive precedence: barrier `B-3A.0a` expressed in the registry.

`CTR-PRIM@v1` is the single entry point to Wave 3A. The five schema packages
`WP-3A-01`..`05` must each consume it and must each declare
`CTR-PRIM:MAJOR_BUMP` in `stale_on[]`. Missing either declaration is the state in
which those five schemas are free to define the shared primitives themselves —
which is what happened in an earlier round, and 3B then amplified the split five
ways into thirteen.
"""

from __future__ import annotations

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-03d"
TITLE = "primitive precedence"

PRIMITIVE_CONTRACT = "CTR-PRIM@v1"
PRIMITIVE_STALE_TRIGGER = "CTR-PRIM:MAJOR_BUMP"

# `06` §5 CI-03d names these producers explicitly; they are the consumers of the
# primitive contract that barrier B-3A.0a guards.
PRIMITIVE_CONSUMERS = ("WP-3A-01", "WP-3A-02", "WP-3A-03", "WP-3A-04", "WP-3A-05")


def run(corpus: Corpus) -> RuleResult:
    """Report Wave 3A schema packages that do not bind to `CTR-PRIM@v1`.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per missing consume or stale-on declaration.
    """
    findings = []
    checked = 0

    for wp_id in PRIMITIVE_CONSUMERS:
        records = corpus.by_wp.get(wp_id)
        if not records:
            continue
        checked += 1
        record = records[0]
        consumes = {str(value) for value in (record.get("contract", {}) or {}).get("consumes", [])}
        stale_on = {str(value) for value in (record.get("stale_on", []) or [])}

        if PRIMITIVE_CONTRACT not in consumes:
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=wp_id,
                    path=corpus.rel(corpus.registry_path),
                    reason=(
                        "Wave 3A schema package does not consume CTR-PRIM@v1; without it the "
                        "five schemas may each define the shared primitives"
                    ),
                    expected=f"{PRIMITIVE_CONTRACT} in contract.consumes[]",
                    actual=", ".join(sorted(consumes)) or "(empty consumes[])",
                )
            )

        if PRIMITIVE_STALE_TRIGGER not in stale_on:
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=wp_id,
                    path=corpus.rel(corpus.registry_path),
                    reason=(
                        "Wave 3A schema package does not go stale on a primitive major bump; "
                        "CTR-PRIM@v2 must supersede all five consuming contracts"
                    ),
                    expected=f"{PRIMITIVE_STALE_TRIGGER} in stale_on[]",
                    actual=", ".join(sorted(stale_on)) or "(empty stale_on[])",
                )
            )

    return RuleResult(rule_id=RULE_ID, findings=tuple(findings), sites=checked, vacuous=not checked)
