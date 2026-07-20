"""CI-02b — orphan file: a produced file no ownership glob claims.

The exclusion set is fixed by `06` §5 and mirrored in the `06` §3.3 glob map:
`registry/build/**`, `.git/**`, `docs/**`, `README.md`, `LICENSE`, `.gitignore`
and `.github/**` are canon documents or generated output, not any package's
production tree. Everything else that exists must have an owner, because an
unowned file is a file no work package is accountable for.

The ownership universe is the registry's `owns[]` axis, not the `06` §3.3 prose
map: `05` §0.1 makes the registry canon and the prose a view of it.
"""

from __future__ import annotations

from typing import Any

from registry.checks.corpus import Corpus
from registry.checks.globs import matches_any, split_globs
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-02b"
TITLE = "orphan file"


def _owned_globs(corpus: Corpus) -> tuple[str, ...]:
    """Collect every ownership glob declared anywhere in the registry.

    Args:
        corpus: The corpus under test.

    Returns:
        (tuple[str, ...]) All globs, regardless of ownership mode.
    """
    globs: set[str] = set()
    for record in corpus.entries:
        for owned in _all_owns(record):
            globs.update(split_globs(str(owned.get("glob", ""))))
    return tuple(sorted(globs))


def _all_owns(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Return package-level and stage-level ownership declarations of a record.

    Args:
        record: A registry record.

    Returns:
        (list[dict[str, Any]]) Ownership entries from `owns[]` and `phases[].owns`.
    """
    owned = list(record.get("owns", []) or [])
    for phase in record.get("phases", []) or []:
        owned.extend(phase.get("owns", []) or [])
    return owned


def run(corpus: Corpus) -> RuleResult:
    """Report produced files that no ownership glob claims.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per unowned file.
    """
    globs = _owned_globs(corpus)
    tree = corpus.artifact_tree

    findings = [
        fail(
            rule_id=RULE_ID,
            req_or_wp="(unowned)",
            path=path,
            reason="file exists in a work-package output tree but no owns[] glob claims it",
            expected="one registry owns[] glob matching this path",
            actual=f"unmatched against {len(globs)} declared ownership glob(s)",
        )
        for path in tree
        if not matches_any(path, globs)
    ]

    return RuleResult(rule_id=RULE_ID, findings=tuple(findings), sites=len(tree), vacuous=not tree)
