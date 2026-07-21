"""CI-11 judges the declaration, not the file that contains it.

`06` §5 anchors CI-11 to a constant declaration carrying an `@target`/`@threshold`
annotation, and naming the wrong unit fails in both directions at once. Too coarse
and one correctly anchored constant excuses every other threshold in its file; too
coarse in the other direction and a file that merely writes the token — a tuple of
annotation tokens, a docstring explaining the rule — is held to a requirement that
was never placed on it. Both directions are asserted here because fixing either one
alone would leave the rule judging something `06` §5 does not name.
"""

from __future__ import annotations

from pathlib import Path

from registry.checks import ci_11
from registry.checks.corpus import Corpus
from registry.checks.fixtures.cases import (
    CI11_UNANCHORED_LINE,
    CI11_UNANCHORED_NAME,
    _ci11_lone_violation,
    _ci11_mentions_only,
    _ci11_violation,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_the_rule_resolves_its_scope() -> None:
    """Vacuity must mean an empty population, never a scope that resolved to nothing.

    CI-11 has no site to judge until measurement code lands, and that is honest. It
    stops being honest the moment the reason is that the rule reads no file at all,
    because from the outside the two look identical: `sites=0`.

    The quantity that separates them is the anchored *package* count, not the source
    count. At Wave -2 every gate-anchored package legitimately owns zero files, so
    asserting on reach would fail on an honest tree while still passing on a corpus
    whose gate axis had been emptied.
    """
    packages = ci_11.anchored_packages(Corpus(REPO_ROOT))
    assert packages, (
        "CI-11 found no package declaring an anchor gate; the gate axis is empty or "
        "the scope stopped resolving, and the rule would stay green through every "
        "violation"
    )


def test_token_mentions_are_not_declarations(tmp_path: Path) -> None:
    """A string naming the annotation and a docstring explaining it are not sites."""
    result = ci_11.run(_ci11_mentions_only(tmp_path))
    assert result.sites == 0, (
        "a tuple of annotation tokens and a docstring were counted as annotated "
        "declarations; 06 §5 puts neither in scope"
    )
    assert not result.findings


def test_lone_annotated_declaration_without_evidence_is_caught(tmp_path: Path) -> None:
    """The base violation still fires: one annotation, one constant, no evidence."""
    result = ci_11.run(_ci11_lone_violation(tmp_path))
    assert len(result.findings) == 1


def test_evidence_elsewhere_in_the_file_does_not_excuse_a_declaration(tmp_path: Path) -> None:
    """An anchored constant does not vouch for the next constant in its file."""
    result = ci_11.run(_ci11_violation(tmp_path))
    assert result.sites == 2, "both annotated declarations should be judged"
    assert len(result.findings) == 1, (
        "the unanchored declaration was excused by the evidence path of the anchored "
        f"one: {[f.as_line() for f in result.findings]}"
    )


def test_finding_locates_the_offending_declaration(tmp_path: Path) -> None:
    """The report names the declaration line, per `02a` §−2.3 acceptance ⑩."""
    finding = ci_11.run(_ci11_violation(tmp_path)).findings[0]
    assert finding.path.endswith(f":{CI11_UNANCHORED_LINE}")
    assert CI11_UNANCHORED_NAME in finding.actual
    assert finding.expected and finding.actual
