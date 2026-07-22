"""Comm-loss watchdog and ERR-nibble fault hold (`WP-2A-07`).

The public surface of the watchdog: the detection loop (`CommLossWatchdog`), its
per-cycle outcome (`WatchdogVerdict`/`WatchdogCause`), and the operator-confirmed
clear path (`OperatorConfirmation`, `ClearErrorCommand`, `UnconfirmedClearError`).
The ERR-nibble decode is reused from `backend.actuation` and is not re-exported here.
"""

from __future__ import annotations

from backend.commloss.constants import (
    CLEAR_ERROR_PAYLOAD,
    DEFAULT_COMM_TIMEOUT_SEC,
    WATCHDOG_GATE_PREFIX,
)
from backend.commloss.watchdog import (
    ClearErrorCommand,
    CommLossWatchdog,
    OperatorConfirmation,
    UnconfirmedClearError,
    WatchdogCause,
    WatchdogVerdict,
)

__all__ = [
    "CLEAR_ERROR_PAYLOAD",
    "DEFAULT_COMM_TIMEOUT_SEC",
    "WATCHDOG_GATE_PREFIX",
    "ClearErrorCommand",
    "CommLossWatchdog",
    "OperatorConfirmation",
    "UnconfirmedClearError",
    "WatchdogCause",
    "WatchdogVerdict",
]
