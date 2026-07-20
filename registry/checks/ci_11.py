"""CI-11 — no target before measurement: a threshold must cite its evidence hash.

`00` invariant I-6 forbids fixing a target before measuring it, and `NFR-PRF-053`
is the requirement behind this rule. The rule is anchored rather than semantic:
it fires only where an anchor exists, meaning a constant declaration annotated
`@target` or `@threshold` inside a package gated on one of the measurement gates
that produce evidence hashes. Such a constant must reference the gate's PASS
evidence directory, otherwise the number is a wish that outranks the measurement.

`06` §5 is explicit that a threshold which cannot carry an anchor is not a CI
matter at all — it moves to acceptance review (§8, F-2 class). So an unannotated
constant is out of scope by design and is not a silent pass.
"""

from __future__ import annotations

from registry.checks.corpus import Corpus
from registry.checks.globs import expand, split_globs
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-11"
TITLE = "no target before measurement"

# `06` §5 names these gates as the anchored set: each produces a PASS evidence hash.
ANCHOR_GATES = ("PG-RT-001a", "PG-RT-001b", "PG-IK-001", "PG-STO-001")

TARGET_ANNOTATIONS = ("@target", "@threshold")

EVIDENCE_ROOT = "registry/build/evidence"

_TEXT_SUFFIXES = frozenset(
    {".py", ".ts", ".tsx", ".js", ".c", ".h", ".cpp", ".hpp", ".yaml", ".yml", ".json", ".toml"}
)


def run(corpus: Corpus) -> RuleResult:
    """Report annotated thresholds that do not cite their gate's evidence hash.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per unanchored annotated threshold.
    """
    findings = []
    sites = 0

    for wp_id, records in sorted(corpus.by_wp.items()):
        gates = {g for record in records for g in record.get("gate", []) or []}
        anchored = [gate for gate in ANCHOR_GATES if gate in gates]
        if not anchored:
            continue

        globs: set[str] = set()
        for record in records:
            owned = list(record.get("owns", []) or [])
            for phase in record.get("phases", []) or []:
                owned.extend(phase.get("owns", []) or [])
            for entry in owned:
                globs.update(split_globs(str(entry.get("glob", ""))))

        for path in sorted(expand(tuple(sorted(globs)), corpus.tracked_files)):
            full = corpus.root / path
            if full.suffix not in _TEXT_SUFFIXES or not full.is_file():
                continue
            text = full.read_text(encoding="utf-8", errors="replace")
            if not any(annotation in text for annotation in TARGET_ANNOTATIONS):
                continue
            sites += 1
            if any(f"{EVIDENCE_ROOT}/{gate}" in text for gate in anchored):
                continue
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=wp_id,
                    path=path,
                    reason=(
                        "source declares an @target/@threshold constant but cites no PASS "
                        "evidence hash for its measurement gate, so a number outranks the "
                        "measurement"
                    ),
                    expected=f"a reference to {EVIDENCE_ROOT}/<{'|'.join(anchored)}>/",
                    actual="annotated constant with no evidence reference",
                )
            )

    return RuleResult(rule_id=RULE_ID, findings=tuple(findings), sites=sites, vacuous=not sites)
