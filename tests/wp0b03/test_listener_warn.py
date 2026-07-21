"""RX-listener check: excess listeners raise a WARN that never blocks (threat (a)).

The full acceptance ① (inject a real ``candump`` into a vcan) is deferred to
``test_deferred_live_vcan``; the WARN *decision* it depends on — right count, WARN
not FAULT, advisory not blocking — runs here against synthetic rcvlist captures.
"""

from __future__ import annotations

from backend.can.intruder.listener import RxListenerCheck
from backend.can.intruder.signals import IntruderSeverity
from tests.wp0b03.synth import make_rcvlist_all


def test_no_excess_no_warning() -> None:
    """Exactly our own listeners produce no warning."""
    check = RxListenerCheck("vcan0", expected_own_listeners=2)
    assert check.evaluate_rcvlist(make_rcvlist_all({"vcan0": 2})) is None


def test_excess_listener_warns_with_correct_count() -> None:
    """A listener beyond our own raises a WARN carrying the accurate counts."""
    check = RxListenerCheck("vcan0", expected_own_listeners=2)
    warning = check.evaluate_rcvlist(make_rcvlist_all({"vcan0": 3}))
    assert warning is not None
    assert warning.observed_listeners == 3
    assert warning.expected_listeners == 2
    assert warning.excess == 1


def test_listener_signal_is_warn_never_fault() -> None:
    """The listener signal's severity is fixed WARN — it cannot be a FAULT."""
    check = RxListenerCheck("vcan0", expected_own_listeners=1)
    warning = check.evaluate_rcvlist(make_rcvlist_all({"vcan0": 2}))
    assert warning is not None
    assert warning.severity is IntruderSeverity.WARN


def test_only_named_iface_counts() -> None:
    """Listeners on another interface do not trip this interface's check."""
    check = RxListenerCheck("vcan0", expected_own_listeners=1)
    assert check.evaluate_rcvlist(make_rcvlist_all({"vcan0": 1, "vcan1": 5})) is None
