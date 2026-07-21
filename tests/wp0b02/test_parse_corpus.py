"""Acceptance ① — parse the whole corpus with 0 false positive / 0 false negative.

Every labeled fixture is parsed and validated, and each parsed field plus the verdict is
checked against `expected.json`. An accept-labeled fixture that fails, or a
reject-labeled fixture that passes, is a false negative / false positive — the corpus
asserts neither occurs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.can.link import parse_link_show, validate_link

_CORPUS = Path(__file__).resolve().parent / "fixtures" / "corpus"
_EXPECTED = json.loads((_CORPUS / "expected.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("filename", sorted(_EXPECTED))
def test_corpus_fixture_parses_and_verdicts_as_labeled(filename: str) -> None:
    """Each fixture's parsed fields and verdict match its recorded expectation."""
    want = _EXPECTED[filename]
    state = parse_link_show((_CORPUS / filename).read_text(encoding="utf-8"), "can0")
    verdict = validate_link(state)

    assert state.fd == want["fd"]
    assert state.bitrate == want["bitrate"]
    assert state.dbitrate == want["dbitrate"]
    assert state.state == want["state"]
    assert state.txqueuelen == want["txqueuelen"]
    assert verdict.ok == want["ok"]
    if want.get("below_recommended"):
        assert verdict.txqueuelen_below_recommended


def test_no_false_positive_or_negative_across_corpus() -> None:
    """No reject-labeled fixture passes, and no accept-labeled fixture fails."""
    false_positives: list[str] = []
    false_negatives: list[str] = []
    for filename, want in _EXPECTED.items():
        state = parse_link_show((_CORPUS / filename).read_text(encoding="utf-8"), "can0")
        ok = validate_link(state).ok
        if ok and not want["ok"]:
            false_positives.append(filename)
        if not ok and want["ok"]:
            false_negatives.append(filename)
    assert false_positives == [], f"rejected link passed verification: {false_positives}"
    assert false_negatives == [], f"valid link was rejected: {false_negatives}"
