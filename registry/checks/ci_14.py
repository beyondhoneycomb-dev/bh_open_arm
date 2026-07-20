"""CI-14 — execution class derives from workflow shape, evaluated per stage.

`00` §4.0 makes `exec_class` a function of `workflow`, not an independent field.
`SHAPE-CF`/`IM`/`IG` are `AI-offline`, `SHAPE-MS` is `AI-on-HW` because it holds
an exclusive rig resource, and only `SHAPE-HG` splits — into `Human-assisted-HW`
or `Human-judgment`, a real distinction because the two carry different cancel
policies.

Evaluation is per *stage*, never per package. A multi-stage package whose second
phase is a measurement must be judged on that phase; collapsing it to one verdict
per package is how an on-hardware stage hides behind an offline one.

`SHAPE-HG` additionally requires the six elements of `00` §4.1 — agent action,
human action, stop condition, safe initial state, produced evidence, resume point
— since a human gate missing any of them is not a gate. Those are written per gate
in `04`, which is where this rule reads them.
"""

from __future__ import annotations

from collections import defaultdict

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail
from registry.checks.wp import SHAPE_HG, SHAPE_TO_EXEC, stages
from registry.ingest.catalog import PG_ID
from registry.ingest.markdown import all_tables, plain_text, read_sections

RULE_ID = "CI-14"
TITLE = "execution class from workflow shape"

SAFETY_DOC = "04-리스크-및-안전-브링업-게이트.md"

# `00` §4.1's six elements, as `04` labels them.
SIX_ELEMENTS = (
    "에이전트가 하는 일",
    "사람이 하는 일",
    "중단조건",
    "안전 초기상태",
    "산출증거",
    "재개지점",
)


def gate_elements(corpus: Corpus) -> dict[str, set[str]]:
    """Index the `00` §4.1 elements documented in `04` by the gate they describe.

    An element block is a `요소`/`내용` table. The gate it belongs to is named by
    the nearest enclosing heading, not inside the table: `04` writes the gate once
    as a section heading (`## 4. PG-SAFE-001 …`) and then one block per bring-up
    stage beneath it. Reading only table bodies finds the gate ids that happen to
    be mentioned in passing and misses the one the block is actually about.

    Args:
        corpus: The corpus under test.

    Returns:
        (dict[str, set[str]]) Gate id to the element labels documented for it.
    """
    path = corpus.plan_dir / SAFETY_DOC
    documented: dict[str, set[str]] = defaultdict(set)
    if not path.is_file():
        return documented

    headings = sorted(
        (
            (section.line, gate)
            for section in read_sections(path)
            for gate in PG_ID.findall(plain_text(section.title))
        ),
        key=lambda item: item[0],
    )

    for table in all_tables(path):
        if not table.header or plain_text(table.header[0]) != "요소":
            continue
        enclosing = [gate for line, gate in headings if line < table.header_line]
        if not enclosing:
            continue
        labels = {plain_text(row[0]).strip() for row in table.rows if row}
        documented[enclosing[-1]].update(labels)
    return documented


def run(corpus: Corpus) -> RuleResult:
    """Report stages whose execution class does not derive from their shape.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per derivation violation or incomplete human gate.
    """
    documented = gate_elements(corpus)
    findings = []
    sites = 0
    reported: set[tuple[str, str, str]] = set()

    for wp_id, records in sorted(corpus.by_wp.items()):
        record = records[0]
        gates = {str(g) for r in records for g in r.get("gate", []) or []}

        for stage in stages(record):
            sites += 1
            allowed = SHAPE_TO_EXEC.get(stage.workflow)
            if allowed is None:
                key = (wp_id, stage.label(), "shape")
                if key not in reported:
                    reported.add(key)
                    findings.append(
                        fail(
                            rule_id=RULE_ID,
                            req_or_wp=f"{wp_id} {stage.label()}",
                            path=corpus.rel(corpus.registry_path),
                            reason=(
                                "stage declares a workflow shape outside the closed "
                                "05 §1.1 vocabulary"
                            ),
                            expected=", ".join(sorted(SHAPE_TO_EXEC)),
                            actual=stage.workflow or "(empty)",
                        )
                    )
                continue

            if stage.exec_class not in allowed:
                key = (wp_id, stage.label(), "class")
                if key not in reported:
                    reported.add(key)
                    findings.append(
                        fail(
                            rule_id=RULE_ID,
                            req_or_wp=f"{wp_id} {stage.label()}",
                            path=corpus.rel(corpus.registry_path),
                            reason=(
                                "stage's execution class is not the one its workflow shape "
                                "derives (00 §4.0)"
                            ),
                            expected=f"{stage.workflow} -> {', '.join(sorted(allowed))}",
                            actual=stage.exec_class or "(empty)",
                        )
                    )

            if stage.workflow != SHAPE_HG:
                continue
            for gate in sorted(g for g in gates if g.startswith("PG-")):
                missing = [
                    label for label in SIX_ELEMENTS if label not in documented.get(gate, set())
                ]
                if not missing:
                    continue
                key = (wp_id, gate, "six")
                if key in reported:
                    continue
                reported.add(key)
                findings.append(
                    fail(
                        rule_id=RULE_ID,
                        req_or_wp=f"{wp_id}/{gate}",
                        path=corpus.rel(corpus.plan_dir / SAFETY_DOC),
                        reason=(
                            "human-gated stage's gate does not document all six elements of "
                            "00 §4.1; a gate missing any of them is not a gate"
                        ),
                        expected=", ".join(SIX_ELEMENTS),
                        actual=f"missing {', '.join(missing)}",
                    )
                )

    return RuleResult(rule_id=RULE_ID, findings=tuple(findings), sites=sites, vacuous=not sites)
