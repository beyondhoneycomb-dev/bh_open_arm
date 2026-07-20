"""CI-05b — unnamed replacement package: `spawns` must name a real catalogue entry.

`06` §5 attaches a fail-closed warning to this rule that is worth honouring
exactly. The search path is *all four* catalogue files that exist. A checker that
looks for a single `02-작업패키지.md` finds no file, therefore finds no work
package ids, therefore judges every `spawns` a phantom — failing closed on a
corpus that is entirely correct. So the rule reads the catalogues the corpus
actually has, and reports the absence of all four as its own failure rather than
laundering it into hundreds of phantom findings.
"""

from __future__ import annotations

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-05b"
TITLE = "unnamed replacement package"


def run(corpus: Corpus) -> RuleResult:
    """Report `spawns` targets that no catalogue defines.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per phantom spawn target.
    """
    if not corpus.catalog_paths:
        return RuleResult(
            rule_id=RULE_ID,
            findings=(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp="(corpus)",
                    path=corpus.rel(corpus.plan_dir),
                    reason=(
                        "no work-package catalogue was found, so no spawn target can be "
                        "verified; the rule fails closed rather than reporting phantoms"
                    ),
                    expected="at least one of 02a/02b/02c/02d present",
                    actual="none of the four catalogue files exist",
                ),
            ),
            sites=0,
        )

    known = set(corpus.catalog)
    findings = []
    sites = 0
    reported: set[str] = set()

    for record in corpus.entries:
        for branch in record.get("negative_branch", []) or []:
            target = str(branch.get("spawns", "") or "").strip()
            if not target:
                continue
            sites += 1
            if target in known or target in reported:
                continue
            reported.add(target)
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=f"{record.get('wp', '?')} -> {target}",
                    path=corpus.rel(corpus.registry_path),
                    reason="negative_branch[].spawns names a work package no catalogue defines",
                    expected=(
                        f"a WP id defined in one of {len(corpus.catalog_paths)} catalogue file(s)"
                    ),
                    actual=target,
                )
            )

    return RuleResult(
        rule_id=RULE_ID,
        findings=tuple(findings),
        sites=sites,
        vacuous=not sites,
        notes=(
            ("no negative_branch[] entry declares a spawns target on this corpus.",)
            if not sites
            else ()
        ),
    )
