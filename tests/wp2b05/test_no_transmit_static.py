"""Acceptance ① — zero CAN transmit on the logger path, and the scan that proves it bites.

This is the load-bearing safety check of WP-2B-05: a logger that transmits is a second CAN
writer (I-1) and drops a brakeless arm, so the shipped logger tree must contain no transmit
symbol, and the scan that says so must genuinely fire on one. Both halves are asserted here.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import backend.friction_log
from backend import actuation
from backend.friction_log.staticcheck import (
    _TRANSMIT_SYMBOLS,
    RULE_CAN_TRANSMIT,
    check_source,
    scan_tree,
    writer_class_names,
)

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


def test_the_scan_covers_every_writer_the_actuation_package_exports() -> None:
    """① Not a written list: the writer names come from the package that holds them.

    A literal list goes stale the moment a writer is added, and it did. `BimanualCanWriter` landed
    in `backend.actuation` and a logger standing one up escaped this scan entirely, while the
    byte-identical `BusCanWriter` version was caught — a FAIL_BLOCKING absence that had stopped
    being checked. Writing the one new name in would have set the same trap for the next writer.
    """
    exported = {
        name
        for name in dir(actuation)
        if inspect.isclass(getattr(actuation, name))
        and hasattr(getattr(actuation, name), "mit_control_batch")
        and hasattr(getattr(actuation, name), "write_count")
    }

    assert exported, "no writer class found; the derivation reads the wrong members"
    assert exported <= _TRANSMIT_SYMBOLS
    # And each is genuinely flagged, not merely listed.
    for name in sorted(exported):
        findings = check_source(f"w = {name}(bus, names)\n", "rogue.py")
        assert [f.rule for f in findings] == [RULE_CAN_TRANSMIT], name


def test_a_writer_added_to_the_actuation_package_is_covered_without_editing_this_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """① The property that makes the derivation worth having, rather than the derivation's output.

    Asserting the four names we happen to have today would pass just as well over a hand-written
    list. What has to hold is that the next writer is covered by the package holding it, with
    nothing here edited.
    """

    class _LaterWriter:
        """A writer added after this scan was written."""

        @property
        def write_count(self) -> int:
            """Writes so far."""
            return 0

        def mit_control_batch(self, batch: object) -> None:
            """Write one batch."""

    monkeypatch.setattr(actuation, _LaterWriter.__name__, _LaterWriter, raising=False)

    assert _LaterWriter.__name__ in writer_class_names()


def test_scan_bites_on_robot_bus_access() -> None:
    """① Reaching `robot.bus` directly is flagged."""
    findings = check_source("handle = robot.bus\n", "rogue.py")
    assert [f.rule for f in findings] == [RULE_CAN_TRANSMIT]


def test_scan_ignores_transmit_symbol_in_a_string() -> None:
    """A transmit word inside a string or comment is not a reference, so it does not fire."""
    source = "note = 'this path never calls mit_control_batch'  # nor send\n"
    assert check_source(source, "x.py") == []
