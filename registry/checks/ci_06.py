"""CI-06 — orphan artifact: a declared output that nothing anchors or that is absent.

`06` §5 gives two failure conditions and either one fails the build: an artifact
path tied to no requirement, and an artifact file that does not exist. The second
has a legitimate escape — a work package that has not run yet declares
`planned: true`, and `06` §2.2 exists precisely so "not built yet" and "silently
missing" stop looking the same.
"""

from __future__ import annotations

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-06"
TITLE = "orphan artifact"

ARTIFACT_REF_PREFIX = "ART-"


def run(corpus: Corpus) -> RuleResult:
    """Report artifacts that are absent without `planned`, or referenced but undeclared.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per missing or unanchored artifact.
    """
    findings = []
    sites = 0
    declared_ids: set[str] = set()
    reported_paths: set[str] = set()

    for record in corpus.entries:
        planned = bool(record.get("planned"))
        owner = f"{record.get('req', '?')}/{record.get('wp', '?')}"
        for artifact in record.get("artifact", []) or []:
            sites += 1
            artifact_id = str(artifact.get("id", "")).strip()
            if artifact_id:
                declared_ids.add(artifact_id)
            path = str(artifact.get("path", "")).strip()
            if not path:
                findings.append(
                    fail(
                        rule_id=RULE_ID,
                        req_or_wp=owner,
                        path=corpus.rel(corpus.registry_path),
                        reason="artifact declares no path, so nothing anchors it to the tree",
                        expected="artifact[].path set",
                        actual="(empty path)",
                    )
                )
                continue
            if (corpus.root / path).exists() or planned or path in reported_paths:
                continue
            reported_paths.add(path)
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=owner,
                    path=path,
                    reason=(
                        "artifact file does not exist and the record does not declare "
                        "planned: true, so 'not built yet' is indistinguishable from lost"
                    ),
                    expected="the file to exist, or planned: true on the record",
                    actual="file absent, planned flag unset",
                )
            )

    # `downstream[]` may name artifacts by id; an id nobody declares is an edge into
    # nothing, and stale propagation would stop there without saying so.
    referenced: dict[str, str] = {}
    for record in corpus.entries:
        for target in record.get("downstream", []) or []:
            target_id = str(target)
            if target_id.startswith(ARTIFACT_REF_PREFIX):
                referenced.setdefault(target_id, str(record.get("wp", "?")))

    for artifact_id, owner in sorted(referenced.items()):
        sites += 1
        if artifact_id in declared_ids:
            continue
        findings.append(
            fail(
                rule_id=RULE_ID,
                req_or_wp=owner,
                path=corpus.rel(corpus.registry_path),
                reason="downstream[] names an artifact id that no artifact[] entry declares",
                expected=f"an artifact[] entry with id {artifact_id}",
                actual="undeclared artifact id",
            )
        )

    return RuleResult(rule_id=RULE_ID, findings=tuple(findings), sites=sites, vacuous=not sites)
