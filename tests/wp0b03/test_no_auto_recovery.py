"""Acceptance ⑤ (RUNS HERE): a latched FAULT attempts zero auto-recovery.

Once the TX watchdog trips a FAULT, the monitor must not try to recover on its own,
no matter how many further polls arrive — including clean ones. The FAULT is latched
until an explicit operator acknowledgement, and the ``recovery_attempts`` counter
must stay 0 throughout, because the monitor has no recovery mechanism at all.
"""

from __future__ import annotations

import pytest

from backend.can.intruder.listener import RxListenerCheck
from backend.can.intruder.monitor import IntruderMonitor, MonitorState, OperatorAckError
from backend.can.intruder.txwatch import TxCounterWatchdog
from tests.wp0b03.synth import make_ip_stats, make_rcvlist_all

_OWN_LISTENERS = 2
_BASELINE_TX = 0


def _faulted_monitor() -> IntruderMonitor:
    """Return a monitor already latched into FAULT by a TX mismatch."""
    monitor = IntruderMonitor(
        RxListenerCheck("vcan0", expected_own_listeners=_OWN_LISTENERS),
        TxCounterWatchdog("vcan0", baseline_tx=_BASELINE_TX),
    )
    monitor.observe_tx(make_ip_stats("vcan0", 7), backend_sent_frames=0)
    assert monitor.state is MonitorState.FAULT
    return monitor


def test_fault_persists_across_clean_polls_with_zero_recovery() -> None:
    """Many further polls, even clean ones, neither recover the fault nor try to."""
    monitor = _faulted_monitor()
    clean_rcvlist = make_rcvlist_all({"vcan0": _OWN_LISTENERS})
    clean_stats = make_ip_stats("vcan0", 0)

    for _ in range(100):
        monitor.observe_listeners(clean_rcvlist)
        # A clean poll would match; the fault must still not lift.
        monitor.observe_tx(clean_stats, backend_sent_frames=0)

    assert monitor.state is MonitorState.FAULT
    assert monitor.may_proceed is False
    assert monitor.recovery_attempts == 0


def test_only_explicit_operator_ack_clears_fault() -> None:
    """The single exit from FAULT is a manual, acknowledged clear — never automatic."""
    monitor = _faulted_monitor()

    with pytest.raises(OperatorAckError):
        monitor.manual_clear("   ")
    assert monitor.state is MonitorState.FAULT
    assert monitor.recovery_attempts == 0

    monitor.manual_clear("operator:mark")
    assert monitor.state is MonitorState.OK
    assert monitor.manual_clears == 1
    # Even an explicit clear is not counted as an *auto*-recovery attempt.
    assert monitor.recovery_attempts == 0
