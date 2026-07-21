"""CAN intruder detection (WP-0B-03), built on the WP-0B-01 flock lock.

`01` FR-SYS-007 was revised after the v2.0 assets: the real intrusion model is not
"response theft" but kernel fan-out. The CAN core copies every matching frame to all
bound sockets, so a passive reader steals nothing — the real hazard is a *second
writer* injecting commands the backend never sent. This package detects that hazard
with two deliberately separate signals, which the WP contract forbids merging:

- `RxListenerCheck` reads ``/proc/net/can/rcvlist_all`` and raises a **WARN** on
  listeners beyond our own. A WARN never blocks — it may be a manual ``candump``.
- `TxCounterWatchdog` reads ``ip -s link show`` and raises a **FAULT** when the link
  TX delta disagrees with the backend's own sent-frame count. A TX intruder can
  register no listener, so it is invisible to the RX check — the watchdog is what
  catches it, and the two checks cover different threats by construction.

`IntruderMonitor` runs both, latches the FAULT with no auto-recovery, and keeps the
two signals on separate channels. `PreflightCheck` (`02` FR-CON-011) asks, before
connect, whether the writer lock is already held (hard, blocks) or whether extra
listeners are present (soft, warns). `reverify_from_fixture` re-runs the identical
checks against real captured output the moment a fixture directory is supplied.
"""

from __future__ import annotations

from backend.can.intruder.listener import RxListenerCheck
from backend.can.intruder.monitor import IntruderMonitor, MonitorState, OperatorAckError
from backend.can.intruder.parse import (
    listeners_for,
    parse_rcvlist_all,
    parse_ss_link,
    parse_tx_packets,
)
from backend.can.intruder.preflight import PreflightCheck, PreflightReport
from backend.can.intruder.probe import can_interfaces, vcan_available
from backend.can.intruder.reverify import (
    ReverifyResult,
    fixture_dir_from_env,
    reverify_from_fixture,
)
from backend.can.intruder.signals import IntruderSeverity, ListenerWarning, TxMismatchFault
from backend.can.intruder.txwatch import TxCounterWatchdog, TxReadError

__all__ = [
    "IntruderMonitor",
    "IntruderSeverity",
    "ListenerWarning",
    "MonitorState",
    "OperatorAckError",
    "PreflightCheck",
    "PreflightReport",
    "RxListenerCheck",
    "ReverifyResult",
    "TxCounterWatchdog",
    "TxMismatchFault",
    "TxReadError",
    "can_interfaces",
    "fixture_dir_from_env",
    "listeners_for",
    "parse_rcvlist_all",
    "parse_ss_link",
    "parse_tx_packets",
    "reverify_from_fixture",
    "vcan_available",
]
