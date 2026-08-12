"""The validator rejects malformed and dishonest ledgers, and accepts a true one.

Acceptance `02a` §1.5 WP-N1-01 ④: five schema-violation fixtures are all rejected.
The fixtures split across the schema and the semantic validator on purpose — a
ledger can be the right shape and still point at ids and quotes that do not
exist, which is the failure a "green but catching nothing" checker would miss.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from registry import SPEC_DIR
from registry.normalization.loader import load_ledger, schema_errors
from registry.normalization.validator import (
    Corpus,
    Violation,
    section_body,
    validate,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "registry" / "normalization" / "fixtures"

FIXTURES = [
    "winner_undefined.yaml",
    "quote_absent.yaml",
    "empty_winners.yaml",
    "enforcement_dangling.yaml",
    "missing_field.yaml",
]


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    """Resolve the corpus once for the semantic checks."""
    return Corpus.load(REPO_ROOT)


def _rejected(corpus: Corpus, name: str) -> bool:
    """Return whether a fixture ledger is rejected by schema or semantics."""
    document = load_ledger(FIXTURE_DIR / name)
    if schema_errors(document):
        return True
    return bool(validate(corpus, document))


@pytest.mark.parametrize("name", FIXTURES)
def test_every_violation_fixture_is_rejected(corpus: Corpus, name: str) -> None:
    """Each of the five fixtures fails validation."""
    assert _rejected(corpus, name)


def test_the_five_fixtures_exist() -> None:
    """Acceptance ④ requires exactly the five named fixtures on disk."""
    present = {path.name for path in FIXTURE_DIR.glob("*.yaml")}
    assert set(FIXTURES) <= present


def test_undefined_winner_is_a_winner_violation(corpus: Corpus) -> None:
    """A winner id that resolves to nothing is reported as a winner violation."""
    document = load_ledger(FIXTURE_DIR / "winner_undefined.yaml")
    kinds = {violation.kind for violation in validate(corpus, document)}
    assert "winner" in kinds


def test_absent_quote_is_a_quote_violation(corpus: Corpus) -> None:
    """A discarded quote that is not in its section is a quote violation."""
    document = load_ledger(FIXTURE_DIR / "quote_absent.yaml")
    kinds = {violation.kind for violation in validate(corpus, document)}
    assert "quote" in kinds


def test_dangling_enforcement_is_an_enforcement_violation(corpus: Corpus) -> None:
    """An enforcement naming a nonexistent CI rule is an enforcement violation."""
    document = load_ledger(FIXTURE_DIR / "enforcement_dangling.yaml")
    kinds = {violation.kind for violation in validate(corpus, document)}
    assert "enforcement" in kinds


def test_section_body_resolves_a_numbered_section() -> None:
    """A quote known to live in 13#3.5 is found in that section body."""
    path = next(SPEC_DIR.glob("13-*.md"))
    body = section_body(path, "3.5")
    assert body is not None
    assert "비상정지, 소프트 스톱" in body


def test_section_body_is_absent_for_a_missing_section() -> None:
    """An unknown section number resolves to None rather than empty text."""
    path = next(SPEC_DIR.glob("13-*.md"))
    assert section_body(path, "99.99") is None


def test_a_top_level_section_is_addressable() -> None:
    """`## N. <title>` resolves, and its body reaches an unnumbered subsection's requirement.

    Every top-level section in the corpus writes the number with a trailing period while every
    subsection writes it bare, so a matcher that demanded whitespace after the digits made the
    whole top-level form uncitable. A row whose only honest citation is a whole section would then
    have had to name a subsection it does not live in — which is a false citation reached by a
    checker's limitation, not by a decision.

    `14` FR-OPS-090 is the live case: it sits under an unnumbered subsection of `14#3`, so `3` is
    the only correct address it has.
    """
    path = next(SPEC_DIR.glob("14-*.md"))
    body = section_body(path, "3")

    assert body is not None
    assert "FR-OPS-090" in body


def test_a_subsection_number_still_does_not_match_its_parent() -> None:
    """Accepting the trailing period must not make `3` match `3.5`; the token is compared whole."""
    path = next(SPEC_DIR.glob("13-*.md"))
    parent = section_body(path, "3")
    child = section_body(path, "3.5")

    assert parent is not None
    assert child is not None
    assert len(child) < len(parent)


def test_violation_renders_one_line() -> None:
    """A violation renders as a single attributable line."""
    line = Violation("NORM-001", "winner", "x has no single corpus definition").as_line()
    assert line.startswith("NORM-001 [winner]")
