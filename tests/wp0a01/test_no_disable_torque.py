"""Acceptance ⑦ — `disable_torque` never appears in the stop path (static).

The stop path is a hold frame, not a torque cut (`04` NFR-MAN-002). Scanning the
whole actuation tree finds zero `disable_torque` references, and the violation
fixture proves the scan actually bites rather than passing vacuously.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.actuation import find_disable_torque

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_ACTUATION_TREE = Path(__file__).resolve().parents[2] / "backend" / "actuation"


def test_stop_path_has_no_disable_torque() -> None:
    """No file in the actuation tree references `disable_torque`."""
    assert find_disable_torque(_ACTUATION_TREE) == []


@pytest.mark.fixture_corpus
def test_disable_torque_fixture_is_flagged() -> None:
    """The violation fixture that cuts torque on stop is caught."""
    violations = find_disable_torque(_FIXTURES)
    flagged = {violation.path.name for violation in violations}
    assert "disable_torque_stop.py" in flagged
    assert all(violation.symbol == "disable_torque" for violation in violations)
