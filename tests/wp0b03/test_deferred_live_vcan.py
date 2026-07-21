"""Deferred acceptance ①②③: live intruder injection against a real vcan.

None of these run on this host — there is no vcan and one cannot be created here — so
every test skips *with a reason* naming what it needs. They are written in full so
that the moment a ``vcan0`` exists (``ip link add dev vcan0 type vcan``), they run
unchanged and exercise the real socket path the synthetic fixtures only stand in for.

The bridge to the synthetic acceptance is the injection harness: the write-only
injector reproduces the acceptance ④ threat (a writer invisible to the RX check) on a
real bus, so ② here and ④ in ``test_distinct_threats`` assert the same property once
against real sockets and once against captured text.
"""

from __future__ import annotations

import time

import pytest

from backend.can.intruder.harness import (
    ActiveWriterInjector,
    PassiveReaderInjector,
    WriteOnlyInjector,
)
from backend.can.intruder.listener import RxListenerCheck
from backend.can.intruder.probe import vcan_available
from backend.can.intruder.txwatch import TxCounterWatchdog

_IFACE = "vcan0"
_NO_VCAN_REASON = (
    f"deferred: needs a live {_IFACE} (ip link add dev {_IFACE} type vcan); "
    "no CAN interface exists on this host and one cannot be created without root"
)

pytestmark = pytest.mark.skipif(not vcan_available(_IFACE), reason=_NO_VCAN_REASON)


def _read_rcvlist() -> str:
    """Capture the live ``/proc/net/can/rcvlist_all`` (only reached with a vcan)."""
    from pathlib import Path

    return Path("/proc/net/can/rcvlist_all").read_text(encoding="utf-8")


def _read_ip_stats(iface: str) -> str:
    """Capture live ``ip -s link show <iface>`` (only reached with a vcan)."""
    import subprocess

    return subprocess.run(
        ["ip", "-s", "link", "show", iface],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test_acceptance_1_passive_reader_warns_without_blocking() -> None:
    """① A manual candump-equivalent raises a WARN and does not block."""
    check = RxListenerCheck(_IFACE, expected_own_listeners=0)
    assert check.evaluate_rcvlist(_read_rcvlist()) is None
    with PassiveReaderInjector(_IFACE):
        warning = check.evaluate_rcvlist(_read_rcvlist())
    assert warning is not None
    assert warning.excess >= 1


def test_acceptance_2_active_writer_faults() -> None:
    """② An active second writer trips the TX watchdog into FAULT."""
    baseline = _tx_now(_IFACE)
    watchdog = TxCounterWatchdog(_IFACE, baseline_tx=baseline)
    with ActiveWriterInjector(_IFACE) as writer:
        writer.inject(20)
        fault = watchdog.evaluate_ip_stats(_read_ip_stats(_IFACE), backend_sent_frames=0)
    assert fault is not None
    assert fault.excess >= 20


def test_acceptance_2_write_only_intruder_faults_but_hides_from_rx() -> None:
    """② (④ on real sockets) A write-only writer faults the watchdog yet hides from RX."""
    rx_check = RxListenerCheck(_IFACE, expected_own_listeners=0)
    baseline = _tx_now(_IFACE)
    watchdog = TxCounterWatchdog(_IFACE, baseline_tx=baseline)
    with WriteOnlyInjector(_IFACE) as writer:
        writer.inject(15)
        rx_missed = rx_check.evaluate_rcvlist(_read_rcvlist()) is None
        fault = watchdog.evaluate_ip_stats(_read_ip_stats(_IFACE), backend_sent_frames=0)
    assert rx_missed
    assert fault is not None


def test_acceptance_3_no_false_positive_when_quiet() -> None:
    """③ With no intruder, neither check fires over a sustained window."""
    rx_check = RxListenerCheck(_IFACE, expected_own_listeners=0)
    watchdog = TxCounterWatchdog(_IFACE, baseline_tx=_tx_now(_IFACE))
    deadline = time.monotonic() + 600.0
    while time.monotonic() < deadline:
        assert rx_check.evaluate_rcvlist(_read_rcvlist()) is None
        assert watchdog.evaluate_ip_stats(_read_ip_stats(_IFACE), backend_sent_frames=0) is None
        time.sleep(5.0)


def _tx_now(iface: str) -> int:
    """Read the current TX counter for baselining (only reached with a vcan)."""
    from backend.can.intruder.parse import parse_tx_packets

    value = parse_tx_packets(_read_ip_stats(iface), iface)
    assert value is not None
    return value
