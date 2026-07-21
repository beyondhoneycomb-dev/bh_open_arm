"""TX-counter watchdog: an unaccounted link TX frame raises a FAULT (threat (b)).

Acceptance ② (inject a real active writer into a vcan) is deferred; the FAULT
decision — TX delta vs backend sent-count, mismatch is FAULT not WARN, unreadable
counter is an error not a silent pass — runs here against synthetic ``ip -s`` output.
"""

from __future__ import annotations

import pytest

from backend.can.intruder.signals import IntruderSeverity
from backend.can.intruder.txwatch import TxCounterWatchdog, TxReadError
from tests.wp0b03.synth import make_ip_stats


def test_matching_tx_no_fault() -> None:
    """When the TX delta equals what the backend sent, there is no fault."""
    watchdog = TxCounterWatchdog("vcan0", baseline_tx=100)
    # baseline 100 + 40 backend frames == observed 140.
    assert watchdog.evaluate_ip_stats(make_ip_stats("vcan0", 140), backend_sent_frames=40) is None


def test_excess_tx_is_fault() -> None:
    """Frames beyond the backend's count (a second writer) raise a FAULT."""
    watchdog = TxCounterWatchdog("vcan0", baseline_tx=100)
    fault = watchdog.evaluate_ip_stats(make_ip_stats("vcan0", 145), backend_sent_frames=40)
    assert fault is not None
    assert fault.observed_tx == 145
    assert fault.expected_tx == 140
    assert fault.excess == 5


def test_missing_backend_frames_is_also_fault() -> None:
    """Backend frames that never reached the wire are a mismatch, hence a FAULT."""
    watchdog = TxCounterWatchdog("vcan0", baseline_tx=100)
    fault = watchdog.evaluate_ip_stats(make_ip_stats("vcan0", 138), backend_sent_frames=40)
    assert fault is not None
    assert fault.excess == -2


def test_tx_signal_is_fault_never_warn() -> None:
    """The TX signal's severity is fixed FAULT — it cannot be a WARN."""
    watchdog = TxCounterWatchdog("vcan0", baseline_tx=0)
    fault = watchdog.evaluate(observed_tx=9, backend_sent_frames=0)
    assert fault is not None
    assert fault.severity is IntruderSeverity.FAULT


def test_unreadable_counter_raises_not_passes() -> None:
    """An unreadable TX counter raises rather than silently reading as zero."""
    watchdog = TxCounterWatchdog("vcan0", baseline_tx=0)
    # The capture names ``can9``, so ``vcan0``'s counter is absent and unreadable.
    unreadable = make_ip_stats("can9", 5)
    with pytest.raises(TxReadError):
        watchdog.evaluate_ip_stats(unreadable, backend_sent_frames=0)
