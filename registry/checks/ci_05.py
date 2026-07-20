"""CI-05 — gate without a negative branch: a gate with no designed failure path.

Every element of `gate[]` needs at least one matching `negative_branch[]` entry.
A gate with no negative branch has only a success path written down, which means
the plan has not decided what happens when it fails — and that decision then gets
made under pressure, by whoever is present.
"""

from __future__ import annotations

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-05"
TITLE = "gate without negative branch"


def run(corpus: Corpus) -> RuleResult:
    """Report gates with no corresponding negative branch.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per uncovered gate.
    """
    findings = []
    sites = 0
    reported: set[tuple[str, str]] = set()

    for record in corpus.entries:
        covered = {
            str(branch.get("gate", "")) for branch in record.get("negative_branch", []) or []
        }
        owner = str(record.get("wp", "?"))
        for gate in record.get("gate", []) or []:
            sites += 1
            gate_id = str(gate)
            if gate_id in covered:
                continue
            key = (owner, gate_id)
            if key in reported:
                continue
            reported.add(key)
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=f"{record.get('req', '?')}/{owner}",
                    path=corpus.rel(corpus.registry_path),
                    reason="gate has no negative_branch entry, so its failure path is undesigned",
                    expected=f"a negative_branch[] entry whose gate is {gate_id}",
                    actual=", ".join(sorted(covered)) or "(negative_branch[] is empty)",
                )
            )

    return RuleResult(rule_id=RULE_ID, findings=tuple(findings), sites=sites, vacuous=not sites)
