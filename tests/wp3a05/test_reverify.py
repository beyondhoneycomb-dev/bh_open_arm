"""The CTR-REC@v1 reverify hook is a real predicate: it passes clean and bites on drift.

`contracts.recorder.reverify.reverify()` is what `WP-3A-06`'s contract regression
checker calls to prove the frozen body, the typed source and `CTR-PRIM@v1` agree.
A hook that could never fail would prove nothing, so this file confirms both that
the shipped contract is consistent and that a drifted body is reported.
"""

from __future__ import annotations

from pathlib import Path

from contracts.recorder import reverify


def test_shipped_contract_reverifies_clean() -> None:
    """Against the committed body and source, reverify finds no inconsistency."""
    assert reverify.reverify() == []


def test_reverify_reports_a_drifted_body(monkeypatch, tmp_path: Path) -> None:
    """A frozen body that no longer matches the emitter is reported as drift."""
    drifted = tmp_path / "schema.json"
    drifted.write_text(reverify.schema.frozen_json_text() + "extra\n", encoding="utf-8")
    monkeypatch.setattr(reverify, "FROZEN_BODY", drifted)
    issues = reverify.reverify()
    assert any("drifted" in issue for issue in issues)


def test_reverify_tolerates_an_absent_draft_body(monkeypatch, tmp_path: Path) -> None:
    """An absent body is the DRAFT state, not a fault: the drift check is vacuous.

    WP-3A-06 materialises and freezes the body; until then its absence must not fail
    reverify, or the consumer could never leave the contract DRAFT.
    """
    monkeypatch.setattr(reverify, "FROZEN_BODY", tmp_path / "absent.json")
    assert reverify.reverify() == []
