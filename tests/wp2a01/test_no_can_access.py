"""Acceptance ① — zero CAN symbol references in the jog producer path (static).

`JointJogProducer` must reach the arm only through the mailbox; it may hold no CAN
handle. This is checked statically because an absence is only honestly provable by
scanning, not by exercising: a runtime test shows the paths it happened to run. The
Wave-1 scan (`find_producer_can_access`) is reused verbatim — the producer tree must
come back clean, and the violation fixture beside this test proves the scan is not
vacuously passing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.actuation import TargetMailbox, find_producer_can_access
from backend.jog import JointJogProducer

_JOG_TREE = Path(__file__).resolve().parents[2] / "backend" / "jog"
_FIXTURES = Path(__file__).resolve().parent / "fixtures"

_CAN_HANDLE_SYMBOLS = {"mit_control_batch", "_mit_control_batch", "CanWriter", "FakeCanWriter"}


def test_jog_producer_path_has_no_can_symbols() -> None:
    """The whole `backend/jog` tree is free of CAN-handle references (acceptance ①)."""
    assert find_producer_can_access(_JOG_TREE) == []


@pytest.mark.fixture_corpus
def test_scan_flags_a_jog_producer_reaching_for_can() -> None:
    """The violation fixture is flagged, so acceptance ①'s scan is not vacuous."""
    violations = find_producer_can_access(_FIXTURES)

    flagged = {violation.path.name for violation in violations}
    assert "jog_producer_can_access.py" in flagged
    assert {violation.symbol for violation in violations} & _CAN_HANDLE_SYMBOLS


def test_producer_surface_exposes_no_can_handle() -> None:
    """The producer holds only its mailbox; its surface has no CAN frame path."""
    producer = JointJogProducer("jog-1", TargetMailbox())

    surface = {name for name in dir(producer) if not name.startswith("_")}
    assert not surface & _CAN_HANDLE_SYMBOLS
    assert surface == {"join", "joined", "producer_id", "publish"}
    # The one reference the producer holds is the mailbox, itself CAN-free.
    assert not {name for name in dir(producer._mailbox) if not name.startswith("_")} & (
        _CAN_HANDLE_SYMBOLS
    )
