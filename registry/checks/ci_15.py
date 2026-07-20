"""CI-15 — read-only measurement: a `SHAPE-MS` stage owns nothing.

`05` §1.1 defines `SHAPE-MS` as reading and measuring on real hardware with no
physical manipulation, holding an exclusive rig resource. A measurement stage that
also owns write paths is no longer only measuring, and the exclusivity argument
that justified its fan-out width of one silently stops describing what it does.

Evaluated per stage, since a multi-stage package may measure in one phase and
build in another; the ownership belongs to the building phase.
"""

from __future__ import annotations

from registry.checks.corpus import Corpus
from registry.checks.globs import split_globs
from registry.checks.model import RuleResult, fail
from registry.checks.wp import SHAPE_MS, stages

RULE_ID = "CI-15"
TITLE = "read-only measurement"


def run(corpus: Corpus) -> RuleResult:
    """Report measurement stages that declare ownership.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per measurement stage that owns paths.
    """
    findings = []
    sites = 0

    for wp_id, records in sorted(corpus.by_wp.items()):
        for stage in stages(records[0]):
            if stage.workflow != SHAPE_MS:
                continue
            sites += 1
            if not stage.owns:
                continue
            globs: list[str] = []
            for entry in stage.owns:
                globs.extend(split_globs(str(entry.get("glob", ""))))
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=f"{wp_id} {stage.label()}",
                    path=corpus.rel(corpus.registry_path),
                    reason=(
                        "measurement stage declares owned paths; SHAPE-MS reads and measures "
                        "only, and ownership contradicts the exclusivity that fixes its width at 1"
                    ),
                    expected="owns[] empty for a SHAPE-MS stage",
                    actual=", ".join(globs) or f"{len(stage.owns)} ownership entries",
                )
            )

    return RuleResult(rule_id=RULE_ID, findings=tuple(findings), sites=sites, vacuous=not sites)
