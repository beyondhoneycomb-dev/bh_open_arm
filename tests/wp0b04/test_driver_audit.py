"""Acceptance ② — the M-24 source reading judges CAN opening with cited lines.

`16` M-24: does `openarm_driver` open CAN in-process? The audit reads a
`driver.py` and cites the exact lines. On this host the real package is absent,
which is recorded honestly (`present=False`, deferred to the reverify hook), and
the scan logic is proven here against synthetic sources plus a cross-check
against the installed `openarm_control`, which M-24 asserts opens no CAN.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from backend.can.bind.driver_audit import (
    audit_driver_source,
    audit_installed_package,
    render_m24_row,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_audit_flags_can_opening_source() -> None:
    """A CAN-opening driver source is judged opens_can=True with cited lines."""
    verdict = audit_driver_source(_FIXTURES / "driver_opens_can.py")
    assert verdict.present is True
    assert verdict.opens_can is True
    assert verdict.cited_lines, "the evidence lines must be cited, not just asserted"
    reasons = {item.reason for item in verdict.cited_lines}
    assert any("CANSocket" in reason or "openarm_can" in reason for reason in reasons)


def test_audit_clears_benign_source() -> None:
    """A CAN-free source is judged opens_can=False — the scan is not a rubber stamp."""
    verdict = audit_driver_source(_FIXTURES / "driver_no_can.py")
    assert verdict.present is True
    assert verdict.opens_can is False
    assert verdict.cited_lines == ()


def test_installed_driver_absent_is_recorded_honestly() -> None:
    """`openarm_driver` absent on this host: present=False, opens_can=None (deferred)."""
    verdict = audit_installed_package()
    assert verdict.present is False
    assert verdict.opens_can is None
    assert "not installed" in verdict.summary
    assert "reverify" in verdict.summary


def test_m24_row_reflects_each_verdict_kind() -> None:
    """The rendered M-24 row states finding and action for each verdict kind."""
    deferred = render_m24_row(audit_installed_package())
    assert "M-24" in deferred and "UNRESOLVED-HERE" in deferred

    opens = render_m24_row(audit_driver_source(_FIXTURES / "driver_opens_can.py"))
    assert "opens CAN" in opens and "EXCLUDED" in opens

    clean = render_m24_row(audit_driver_source(_FIXTURES / "driver_no_can.py"))
    assert "no CAN-socket open" in clean


def test_installed_openarm_control_opens_no_can() -> None:
    """Cross-check M-24: the installed openarm_control opens CAN in none of its sources."""
    spec = importlib.util.find_spec("openarm_control")
    if spec is None or not spec.submodule_search_locations:
        pytest.skip("openarm_control not installed on this host")
    offenders: list[str] = []
    for location in spec.submodule_search_locations:
        for source in sorted(Path(location).rglob("*.py")):
            if audit_driver_source(source).opens_can:
                offenders.append(str(source))
    assert offenders == [], f"M-24 says openarm_control opens no CAN; these did: {offenders}"
