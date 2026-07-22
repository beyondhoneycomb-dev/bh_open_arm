"""Acceptance ① — zero CAN transmit on the logger path, and the scan that proves it bites.

This is the load-bearing safety check of WP-2B-05: a logger that transmits is a second CAN
writer (I-1) and drops a brakeless arm, so the shipped logger tree must contain no transmit
symbol, and the scan that says so must genuinely fire on one. Both halves are asserted here.
"""

from __future__ import annotations

from pathlib import Path

import backend.friction_log
from backend.friction_log.staticcheck import RULE_CAN_TRANSMIT, check_source, scan_tree

_FRICTION_LOG_ROOT = Path(backend.friction_log.__file__).resolve().parent


def test_logger_tree_has_no_transmit_symbol() -> None:
    """① The shipped `backend/friction_log` tree names no CAN transmit symbol."""
    transmit = [f for f in scan_tree(_FRICTION_LOG_ROOT) if f.rule == RULE_CAN_TRANSMIT]
    assert transmit == []


def test_scan_bites_on_can_writer_import() -> None:
    """① Importing the CAN-writer module is flagged."""
    findings = check_source("import backend.actuation.can_writer\n", "rogue.py")
    assert [f.rule for f in findings] == [RULE_CAN_TRANSMIT]


def test_scan_bites_on_from_import_of_writer() -> None:
    """① A `from backend.actuation.can_writer import ...` is flagged."""
    findings = check_source("from backend.actuation.can_writer import CanWriter\n", "rogue.py")
    assert RULE_CAN_TRANSMIT in {f.rule for f in findings}


def test_scan_bites_on_mit_control_batch_call() -> None:
    """① Calling `mit_control_batch` is flagged."""
    findings = check_source("writer.mit_control_batch(batch)\n", "rogue.py")
    assert [f.rule for f in findings] == [RULE_CAN_TRANSMIT]


def test_scan_bites_on_socket_send_family() -> None:
    """① Any socket send call is flagged."""
    for symbol in ("send", "sendall", "sendto", "sendmsg"):
        findings = check_source(f"sock.{symbol}(frame)\n", "rogue.py")
        assert [f.rule for f in findings] == [RULE_CAN_TRANSMIT], symbol


def test_scan_bites_on_robot_bus_access() -> None:
    """① Reaching `robot.bus` directly is flagged."""
    findings = check_source("handle = robot.bus\n", "rogue.py")
    assert [f.rule for f in findings] == [RULE_CAN_TRANSMIT]


def test_scan_ignores_transmit_symbol_in_a_string() -> None:
    """A transmit word inside a string or comment is not a reference, so it does not fire."""
    source = "note = 'this path never calls mit_control_batch'  # nor send\n"
    assert check_source(source, "x.py") == []
