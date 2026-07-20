"""CI-11b-자기적용 — prove CI-11b runs, catches, and does not over-block.

`06` §5 declares this as a rule in its own right, not a clause of `CI-11b`, and
states the reason: "a checker that has not been run merely exists syntactically;
its operation is unproven." A seal nobody exercised is indistinguishable from a
seal that matches nothing, and the second one is worse because it is trusted.

Three conditions, all required:

1. A violation planted at each declaration site — a manifest `gates:` value and
   this registry's `gate[]` value — is rejected.
2. Prose using the bare id as a gate *family* is not rejected. Those sentences
   name the axis rather than picking a side of the split, and a checker that
   reached into prose would fail on the very text documenting the ban.
3. The `00`, `04` and `06` originals are green as they stand.
"""

from __future__ import annotations

from registry.checks import ci_11b
from registry.checks.corpus import Corpus, GateCell
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-11b-자기적용"
TITLE = "CI-11b green on its own corpus"

UNDIVIDED_GATE = "PG-RT-001"
SPLIT_GATE = "PG-RT-001a"

PLANTED_SITES = (
    ("manifest gates: value", "manifest-gates"),
    ("registry gate[] value", "registry-gate"),
)

ORIGINAL_DOCUMENTS = (
    "00-실행계획-개요.md",
    "04-리스크-및-안전-브링업-게이트.md",
    "06-추적성-레지스트리.md",
)


class _PlantedCorpus:
    """A corpus view whose declaration sites are supplied rather than read.

    CI-11b consumes exactly one property. Substituting it is how the seal gets
    exercised against a known violation without writing a violation into the
    real repository, where it would be indistinguishable from a genuine defect.
    """

    def __init__(self, base: Corpus, cells: tuple[GateCell, ...]) -> None:
        self._base = base
        self.gate_declaration_sites = cells

    def __getattr__(self, name: str) -> object:
        return getattr(self._base, name)


def _cell(value: str, site: str) -> GateCell:
    """Build one declaration-site cell carrying the given value."""
    return GateCell(
        value=value,
        path="registry/checks/fixtures/ci_11b_self",
        line=0,
        site=site,
        owner="WP-BOOT-03",
    )


def run(corpus: Corpus) -> RuleResult:
    """Exercise CI-11b against planted violations, a named exception, and the corpus.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per unmet condition.
    """
    findings = []

    for label, site in PLANTED_SITES:
        planted = _PlantedCorpus(corpus, (_cell(UNDIVIDED_GATE, site),))
        if not ci_11b.run(planted).findings:  # type: ignore[arg-type]
            findings.append(
                fail(
                    RULE_ID,
                    label,
                    "registry/checks/ci_11b.py",
                    "CI-11b did not reject the undivided gate id planted at a declaration "
                    "site; a seal that catches nothing forges evidence that it holds",
                    expected="one finding",
                    actual="none",
                )
            )

    permitted = _PlantedCorpus(corpus, (_cell(SPLIT_GATE, "registry-gate"),))
    if ci_11b.run(permitted).findings:  # type: ignore[arg-type]
        findings.append(
            fail(
                RULE_ID,
                "split id accepted",
                "registry/checks/ci_11b.py",
                "CI-11b rejected PG-RT-001a; the ban covers the undivided id, not the "
                "gate family, and over-blocking breaks the split it exists to enforce",
                expected="no finding",
                actual="rejected",
            )
        )

    flagged = {finding.path for finding in ci_11b.run(corpus).findings}
    for document in ORIGINAL_DOCUMENTS:
        if any(document in path for path in flagged):
            findings.append(
                fail(
                    RULE_ID,
                    document,
                    f"docs/plan/{document}",
                    "CI-11b is not green on the corpus as it stands, so either the document "
                    "carries a real violation or the checker over-blocks its own rationale",
                )
            )

    sites = len(PLANTED_SITES) + 1 + len(ORIGINAL_DOCUMENTS)
    return RuleResult(rule_id=RULE_ID, findings=tuple(findings), sites=sites, vacuous=False)
