"""The seals must not catch the text that documents them.

`02a` §−2.3 acceptance ⑤. CI-10 and CI-11b ban two identifiers from gate
declaration sites. Both bans are explained at length in the planning documents,
and those explanations write the banned identifiers in prose. A checker scoped by
lexical search over `docs/plan/**` therefore fails on its own justification the
first time it runs — the recursion `06` §5 names explicitly.

These tests assert both halves: the prose is numerous and passes, the field values
fail. Asserting only the second half would leave the trap undetected.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from registry.checks import ci_10, ci_11b
from registry.checks.corpus import Corpus
from registry.checks.fixtures import corpus as fixture_corpus
from registry.checks.fixtures.cases import _ci10_violation, _ci11b_violation

REPO_ROOT = Path(__file__).resolve().parents[2]

BARE_M8 = re.compile(r"\bM-8\b")
BARE_PG_RT_001 = re.compile(r"PG-RT-001(?![ab0-9])")

# Below this, "the prose says it a lot" would not be an honest claim.
SUBSTANTIAL_PROSE_MENTIONS = 15


def _prose_mentions(pattern: re.Pattern[str]) -> int:
    """Count occurrences of a pattern across the planning documents.

    Args:
        pattern: Identifier pattern to count.

    Returns:
        (int) Total occurrences.
    """
    return sum(
        len(pattern.findall(path.read_text(encoding="utf-8")))
        for path in sorted((REPO_ROOT / "docs" / "plan").glob("*.md"))
    )


@pytest.mark.parametrize(
    ("pattern", "label"),
    ((BARE_M8, "M-8"), (BARE_PG_RT_001, "PG-RT-001")),
)
def test_prose_writes_the_banned_identifier_many_times(
    pattern: re.Pattern[str], label: str
) -> None:
    """The documents really do write the banned identifier in prose."""
    mentions = _prose_mentions(pattern)
    assert mentions >= SUBSTANTIAL_PROSE_MENTIONS, (
        f"only {mentions} prose mentions of {label}; if this dropped, the trap these "
        "rules avoid may no longer be real and the scoping should be re-justified"
    )


@pytest.mark.parametrize("module", (ci_10, ci_11b), ids=("CI-10", "CI-11b"))
def test_seals_are_green_on_the_real_corpus(module) -> None:
    """Neither seal fires on the corpus that documents it."""
    result = module.run(Corpus(REPO_ROOT))
    assert result.sites > 0, f"{module.RULE_ID} examined no declaration sites"
    assert not result.findings, (
        f"{module.RULE_ID} fired on the corpus that documents the ban: "
        f"{[f.as_line() for f in result.findings]}"
    )


@pytest.mark.parametrize(
    ("module", "builder"),
    ((ci_10, _ci10_violation), (ci_11b, _ci11b_violation)),
    ids=("CI-10", "CI-11b"),
)
def test_seals_fail_on_field_values(module, builder, tmp_path: Path) -> None:
    """Both seals reject the identifier when it occupies a field value."""
    result = module.run(builder(tmp_path))
    assert result.findings, f"{module.RULE_ID} accepted the banned id as a field value"
    assert {f.actual for f in result.findings} != set()


@pytest.mark.parametrize("module", (ci_10, ci_11b), ids=("CI-10", "CI-11b"))
def test_seals_ignore_prose_placed_in_a_non_field_position(module, tmp_path: Path) -> None:
    """A sentence containing the identifier is not a declaration site."""
    from registry.checks.corpus import GateCell

    prose = GateCell(
        value="control-loop measurement must use PG-RT-001a, never the M-8 of 16 §8",
        path="docs/plan/00-실행계획-개요.md",
        line=1,
        site="prose-not-a-site",
        owner="(narration)",
    )
    result = module.run(fixture_corpus(gate_declaration_sites=(prose,)))
    assert not result.findings, (
        f"{module.RULE_ID} matched inside a sentence; the rule must compare whole "
        "field values, not search for a substring"
    )
