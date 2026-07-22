"""Acceptance ② — `record_loop()`'s `stop_recording` is not wired to the E-Stop (static).

`stop_recording` is episode control: it leaves the loop without holding the motors, so
wiring it to a safety stop drops the arm (`FR-SAF-073`, `12` §2.7.2). Scanning the whole
reaction tree finds zero references, and the violation fixture proves the scan bites
rather than passing vacuously (the WP-BOOT-03 discipline).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.reaction import find_estop_stop_recording_wiring

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_REACTION_TREE = Path(__file__).resolve().parents[2] / "backend" / "reaction"


def test_reaction_tree_has_no_stop_recording_wiring() -> None:
    """No file in the reaction tree references `record_loop`/`stop_recording`."""
    assert find_estop_stop_recording_wiring(_REACTION_TREE) == []


@pytest.mark.fixture_corpus
def test_stop_recording_estop_fixture_is_flagged() -> None:
    """The violation fixture that wires `stop_recording` to a latch is caught."""
    violations = find_estop_stop_recording_wiring(_FIXTURES)
    flagged = {violation.path.name for violation in violations}
    assert "estop_via_stop_recording.py" in flagged
    assert any(violation.symbol == "stop_recording" for violation in violations)
