"""CI-07 — normalization hash: a contested requirement must cite the ledger entry.

The trigger is an enumerable list, not a prose predicate. `06` §5 is explicit
about this: the `NORM-*` rows of the Wave −1 normalization ledger (`02a` §1.3) name
the requirements whose meaning was in dispute, and any record touching one of them
— or tagged `결정필요` — must carry the ledger hash that records how the dispute
was settled. Without it, the record silently picks one of the two readings.

`wp == DEFERRED` is exempt: deferred work has not chosen a reading yet.
"""

from __future__ import annotations

import re

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail
from registry.ingest.catalog import REQ_ID
from registry.ingest.markdown import all_tables, plain_text

RULE_ID = "CI-07"
TITLE = "normalization hash"

WP_DEFERRED = "DEFERRED"
TAG_DECISION_REQUIRED = "결정필요"
LEDGER_DOC = "02a-작업패키지-Wave-minus1-to-1.md"

NORM_ROW = re.compile(r"^NORM-\d{3}$")

# The ledger row states a contradiction and its resolution. Only the columns that
# name the requirements whose *meaning* was in dispute make those requirements
# contested: the contradiction, the winner, the discarded readings. The rationale
# and enforcement columns cite other requirements to *justify* the ruling — a
# requirement named there was the evidence or the assert, not a side of the
# dispute, and harvesting it fabricates a contested record (the mention-is-not-a-
# declaration trap, `02a` §1.2 column semantics).
CONTESTED_COLUMNS = ("모순", "승리 요구사항", "폐기 텍스트")


def ledger_requirements(corpus: Corpus) -> frozenset[str]:
    """Collect the requirement ids the Wave −1 ledger records as contested.

    Args:
        corpus: The corpus under test.

    Returns:
        (frozenset[str]) Requirement ids named in a `NORM-*` row's contested columns.
    """
    path = corpus.plan_dir / LEDGER_DOC
    if not path.is_file():
        return frozenset()
    requirements: set[str] = set()
    for table in all_tables(path):
        columns = [table.column_index(name) for name in CONTESTED_COLUMNS]
        contested = [index for index in columns if index is not None]
        if not contested:
            continue
        for row in table.rows:
            if not row or not NORM_ROW.match(plain_text(row[0]).strip()):
                continue
            for index in contested:
                if index < len(row):
                    requirements.update(REQ_ID.findall(plain_text(row[index])))
    return frozenset(requirements)


def run(corpus: Corpus) -> RuleResult:
    """Report records that must cite a normalization hash but do not.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per record missing its ledger hash.
    """
    contested = ledger_requirements(corpus)

    findings = []
    sites = 0
    for record in corpus.entries:
        req = str(record.get("req", ""))
        tag = str(record.get("tag", ""))
        if req not in contested and tag != TAG_DECISION_REQUIRED:
            continue
        sites += 1
        if record.get("wp") == WP_DEFERRED:
            continue
        if record.get("normalization"):
            continue
        trigger = "NORM-* ledger entry" if req in contested else f"tag={TAG_DECISION_REQUIRED}"
        findings.append(
            fail(
                rule_id=RULE_ID,
                req_or_wp=f"{req}/{record.get('wp', '?')}",
                path=corpus.rel(corpus.registry_path),
                reason=(
                    f"record is under {trigger} but declares no normalization hash, so it "
                    "silently adopts one reading of a contested requirement"
                ),
                expected="normalization: sha256:<hex> citing the Wave -1 ledger",
                actual="normalization is null",
            )
        )

    return RuleResult(rule_id=RULE_ID, findings=tuple(findings), sites=sites, vacuous=not sites)
