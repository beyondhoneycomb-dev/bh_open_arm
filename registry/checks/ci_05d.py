"""CI-05d — no invented retry package: re-running is a state, not a new package.

`06` §2.6 makes re-execution the `RETRY_WITH_VARIANT` state of the original gate.
A `spawns` target of the form `WP-<original>R`, or any id built by suffixing an
existing package id without a catalogue definition, is the plan minting work
package ids outside `02a`–`02d`, where the sole issuing authority lives.
"""

from __future__ import annotations

import re

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-05d"
TITLE = "no invented retry package"

RETRY_SUFFIX = re.compile(r"^(?P<base>WP-[A-Z0-9]+-[SG]?\d{1,2})(?P<suffix>[A-Za-z0-9_-]+)$")


def run(corpus: Corpus) -> RuleResult:
    """Report spawn targets built by suffixing an existing package id.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per invented retry package.
    """
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
            match = RETRY_SUFFIX.match(target)
            if not match or match.group("base") not in known:
                continue
            reported.add(target)
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=f"{record.get('wp', '?')} -> {target}",
                    path=corpus.rel(corpus.registry_path),
                    reason=(
                        "spawn target is an existing package id plus a suffix with no catalogue "
                        "definition; re-execution is the RETRY_WITH_VARIANT state, not a new "
                        "package"
                    ),
                    expected=f"the RETRY_WITH_VARIANT state on {match.group('base')}",
                    actual=target,
                )
            )

    return RuleResult(rule_id=RULE_ID, findings=tuple(findings), sites=sites, vacuous=not sites)
