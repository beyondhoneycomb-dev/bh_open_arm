"""Acceptance ⑨ — the crash-report document states the software cannot prevent a drop.

NFR-SAF-009 anti-overconfidence check: the contract document must carry the load-bearing fact
in words. The static check must (a) confirm the shipped document contains the phrase, and (b)
bite on text that omits it — a check that passes vacuously would defeat its whole purpose. The
rendered crash report must also embed the disclaimer, so a report can never read as reassuring.
"""

from __future__ import annotations

import pytest

from ops.telemetry.crash_report import CrashReport
from ops.telemetry.drop_disclaimer import (
    CRASH_REPORT_CONTRACT_DOC,
    DROP_DISCLAIMER,
    REQUIRED_DISCLAIMER_PHRASE,
    MissingDropDisclaimerError,
    assert_disclaimer_present,
    contains_disclaimer,
    doc_has_disclaimer,
)


def test_contract_document_carries_the_disclaimer() -> None:
    """The shipped crash-report contract document contains the required phrase."""
    assert CRASH_REPORT_CONTRACT_DOC.is_file()
    assert doc_has_disclaimer()
    assert REQUIRED_DISCLAIMER_PHRASE in CRASH_REPORT_CONTRACT_DOC.read_text(encoding="utf-8")


def test_disclaimer_check_bites_on_omitting_text() -> None:
    """Text without the phrase is rejected — the check is not vacuous."""
    assert not contains_disclaimer("all systems nominal; the watchdog has you covered")
    with pytest.raises(MissingDropDisclaimerError):
        assert_disclaimer_present("all systems nominal")


def test_canonical_disclaimer_states_the_safety_fact() -> None:
    """The canonical disclaimer constant embeds the phrase and cites NFR-SAF-009."""
    assert REQUIRED_DISCLAIMER_PHRASE in DROP_DISCLAIMER
    assert "NFR-SAF-009" in DROP_DISCLAIMER


def test_rendered_crash_report_embeds_the_disclaimer() -> None:
    """A rendered crash report always carries the disclaimer — never reads as reassuring."""
    report = CrashReport(
        pid=1234,
        exit_code=137,
        signal=9,
        ring_buffer=(),
        last_transition=None,
        backtrace=None,
    )
    assert REQUIRED_DISCLAIMER_PHRASE in report.render()
    assert REQUIRED_DISCLAIMER_PHRASE in report.to_dict()["disclaimer"]
