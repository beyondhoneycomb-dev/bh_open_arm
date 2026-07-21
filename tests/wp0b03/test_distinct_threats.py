"""Acceptance ④ (RUNS HERE): the two checks cover genuinely different threats.

The scenario is a TX intruder that registers *no* listener: RX listeners are exactly
our own (zero excess), while the link TX counter shows frames we never sent. The
RX-listener check must *miss* it and the TX watchdog must *catch* it — proving that
neither check subsumes the other and that merging them would lose the threat one of
them alone sees. This also exercises the contract that WARN and FAULT are distinct,
never-merged signals held on separate channels.
"""

from __future__ import annotations

from backend.can.intruder.listener import RxListenerCheck
from backend.can.intruder.monitor import IntruderMonitor, MonitorState
from backend.can.intruder.signals import IntruderSeverity
from backend.can.intruder.txwatch import TxCounterWatchdog
from tests.wp0b03.synth import make_ip_stats, make_rcvlist_all

# Our process opens a reader and a writer socket: two legitimate receive-all rows.
_OWN_LISTENERS = 2
_BASELINE_TX = 500
_BACKEND_SENT = 60
# The intruder injects frames beyond what the backend accounts for.
_INTRUDER_TX = 9


def _tx_only_intruder_captures() -> tuple[str, str]:
    """Return (rcvlist, ip_stats) for a TX-only intruder: 0 RX excess, extra TX."""
    rcvlist = make_rcvlist_all({"vcan0": _OWN_LISTENERS})
    ip_stats = make_ip_stats("vcan0", _BASELINE_TX + _BACKEND_SENT + _INTRUDER_TX)
    return rcvlist, ip_stats


def test_rx_check_misses_tx_only_intruder() -> None:
    """(a) The RX-listener check sees no excess — it is blind to a TX-only writer."""
    rcvlist, _ = _tx_only_intruder_captures()
    check = RxListenerCheck("vcan0", expected_own_listeners=_OWN_LISTENERS)
    assert check.evaluate_rcvlist(rcvlist) is None


def test_tx_watchdog_catches_tx_only_intruder() -> None:
    """(b) The TX watchdog catches exactly what the RX check missed."""
    _, ip_stats = _tx_only_intruder_captures()
    watchdog = TxCounterWatchdog("vcan0", baseline_tx=_BASELINE_TX)
    fault = watchdog.evaluate_ip_stats(ip_stats, backend_sent_frames=_BACKEND_SENT)
    assert fault is not None
    assert fault.excess == _INTRUDER_TX


def test_monitor_reports_fault_from_tx_channel_only() -> None:
    """End to end: the monitor goes to FAULT with no warning standing on the RX channel."""
    rcvlist, ip_stats = _tx_only_intruder_captures()
    monitor = IntruderMonitor(
        RxListenerCheck("vcan0", expected_own_listeners=_OWN_LISTENERS),
        TxCounterWatchdog("vcan0", baseline_tx=_BASELINE_TX),
    )
    assert monitor.observe_listeners(rcvlist) is None
    assert monitor.observe_tx(ip_stats, backend_sent_frames=_BACKEND_SENT) is not None

    assert monitor.state is MonitorState.FAULT
    assert monitor.warning is None
    assert monitor.fault is not None
    assert not monitor.may_proceed


def test_warn_and_fault_are_distinct_channels() -> None:
    """A WARN and a FAULT coexist on separate channels; neither is merged into the other."""
    # An excess listener (WARN) AND an extra TX frame (FAULT) at the same time.
    rcvlist = make_rcvlist_all({"vcan0": _OWN_LISTENERS + 1})
    ip_stats = make_ip_stats("vcan0", _BASELINE_TX + _BACKEND_SENT + _INTRUDER_TX)
    monitor = IntruderMonitor(
        RxListenerCheck("vcan0", expected_own_listeners=_OWN_LISTENERS),
        TxCounterWatchdog("vcan0", baseline_tx=_BASELINE_TX),
    )
    warning = monitor.observe_listeners(rcvlist)
    fault = monitor.observe_tx(ip_stats, backend_sent_frames=_BACKEND_SENT)

    assert warning is not None and warning.severity is IntruderSeverity.WARN
    assert fault is not None and fault.severity is IntruderSeverity.FAULT
    # Both signals are retained, on their own channels; the FAULT dominates the state.
    assert monitor.warning is warning
    assert monitor.fault is fault
    assert monitor.state is MonitorState.FAULT
