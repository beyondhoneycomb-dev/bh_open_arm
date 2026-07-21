"""The validator rejects malformed and dishonest ledgers, and accepts a true one.

Acceptance `02a` §1.5 WP-N1-01 ④: five schema-violation fixtures are all rejected.
The fixtures split across the schema and the semantic validator on purpose — a
ledger can be the right shape and still point at ids and quotes that do not
exist, which is the failure a "green but catching nothing" checker would miss.
"""

from __future__ import annotations

from pathlib import Path

import pytest

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
    path = next((REPO_ROOT / "docs" / "spec").glob("13-*.md"))
    body = section_body(path, "3.5")
    assert body is not None
    assert "비상정지, 소프트 스톱" in body


def test_section_body_is_absent_for_a_missing_section() -> None:
    """An unknown section number resolves to None rather than empty text."""
    path = next((REPO_ROOT / "docs" / "spec").glob("13-*.md"))
    assert section_body(path, "99.99") is None


def test_violation_renders_one_line() -> None:
    """A violation renders as a single attributable line."""
    line = Violation("NORM-001", "winner", "x has no single corpus definition").as_line()
    assert line.startswith("NORM-001 [winner]")
