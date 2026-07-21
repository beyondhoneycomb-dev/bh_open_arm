"""The WP-0B-03 intruder adapter: a live second *writer* also gates is_connected.

A `TxCounterWatchdog` FAULT (unaccounted TX frames = a second writer, `12` §2.9)
is the double bind the flock cannot see. `IntruderBindProbe` maps it to a foreign
binder so the gate refuses on it exactly as it does on a flock holder. The WARN
listener is deliberately not a binder — a passive reader steals nothing under
fan-out (`01` FR-SYS-007 revised) — which the adapter enforces by accepting only
faults. Live TX reads need vcan, so feeding the probe from a running watchdog is
deferred; the mapping is verified here against a synthetic fault.
"""

from __future__ import annotations

from backend.can.bind.connection_gate import ConnectionGate
from backend.can.bind.double_bind import DoubleBindCheck
from backend.can.bind.intruder_probe import SOURCE_TX_WATCHDOG, IntruderBindProbe
from backend.can.intruder.signals import TxMismatchFault


def _transport_up() -> bool:
    """A transport probe that always reports connected."""
    return True


def test_tx_fault_maps_to_a_foreign_binder() -> None:
    """A TX-mismatch fault becomes a foreign binder tagged as the TX watchdog."""
    fault = TxMismatchFault(iface="can0", observed_tx=1200, expected_tx=1000)
    binders = IntruderBindProbe([fault]).foreign_binders(["can0"])
    assert [binder.source for binder in binders] == [SOURCE_TX_WATCHDOG]
    assert binders[0].holder_pid is None  # the watchdog sees frames, not a PID


def test_gate_refuses_on_a_tx_intruder() -> None:
    """The gate refuses to report connected when a second writer is on the bus."""
    fault = TxMismatchFault(iface="can0", observed_tx=1200, expected_tx=1000)
    gate = ConnectionGate(DoubleBindCheck([IntruderBindProbe([fault])]))
    assert gate.is_connected(["can0"], _transport_up) is False


def test_tx_fault_is_scoped_to_its_interface() -> None:
    """A TX fault on can1 does not gate a report about can0."""
    fault = TxMismatchFault(iface="can1", observed_tx=50, expected_tx=0)
    gate = ConnectionGate(DoubleBindCheck([IntruderBindProbe([fault])]))
    assert gate.is_connected(["can0"], _transport_up) is True
    assert gate.is_connected(["can1"], _transport_up) is False


def test_no_faults_means_no_binders() -> None:
    """With no TX fault (a listener-only bus is advisory), the adapter gates nothing."""
    gate = ConnectionGate(DoubleBindCheck([IntruderBindProbe([])]))
    assert gate.is_connected(["can0"], _transport_up) is True
