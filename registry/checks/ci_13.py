"""CI-13 — stale set not updated: changing a gate state must move `stale_set.json`.

`06` §4.4 propagates invalidation from gate state, so a commit that changes a gate
state without touching the stale set has changed the truth without changing what
depends on it. The descendants stay green while resting on a verdict that moved.

This rule reads the working commit rather than the registry: it is a property of a
change, not of a state.
"""

from __future__ import annotations

import subprocess

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-13"
TITLE = "stale set not updated"

STALE_SET = "registry/state/stale_set.json"

# Paths whose change means a gate verdict moved.
GATE_STATE_PATHS = ("registry/state/gates", "registry/build/gate_index.json")


def changed_paths(corpus: Corpus, revision: str) -> tuple[str, ...]:
    """List the paths a revision touched.

    Args:
        corpus: The corpus under test.
        revision: Git revision to inspect.

    Returns:
        (tuple[str, ...]) Root-relative paths, empty when the revision is unreadable.
    """
    result = subprocess.run(
        ["git", "-c", "core.quotePath=false", "show", "--name-only", "--pretty=format:", revision],
        cwd=corpus.root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ()
    return tuple(line for line in result.stdout.splitlines() if line.strip())


def run(corpus: Corpus, revision: str = "HEAD") -> RuleResult:
    """Report a gate-state change that does not update the stale set.

    Args:
        corpus: The corpus under test.
        revision: Git revision to inspect.

    Returns:
        (RuleResult) A finding when gate state moved without the stale set.
    """
    touched = changed_paths(corpus, revision)
    gate_changes = [p for p in touched if p.startswith(GATE_STATE_PATHS)]

    findings = []
    if gate_changes and STALE_SET not in touched:
        findings.append(
            fail(
                rule_id=RULE_ID,
                req_or_wp=revision,
                path=", ".join(sorted(gate_changes)[:4]),
                reason=(
                    "commit changes gate state without a stale_set.json diff, so descendants "
                    "stay green while resting on a verdict that moved"
                ),
                expected=f"{STALE_SET} in the same commit",
                actual=f"{len(touched)} path(s) changed, stale set untouched",
            )
        )

    return RuleResult(
        rule_id=RULE_ID,
        findings=tuple(findings),
        sites=len(gate_changes),
        vacuous=not gate_changes,
        notes=(
            (f"revision {revision} touches no gate-state path, so nothing to verify.",)
            if not gate_changes
            else ()
        ),
    )
