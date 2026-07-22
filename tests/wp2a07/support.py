"""Builders and synthetic-frame helpers for the WP-2A-07 watchdog suite.

The helpers keep every test reading in the same vocabulary: `status_byte` packs an
ERR nibble the way a Damiao `data[0]` carries it, `frames` is a `recv_all()` that
injects those bytes on the next cycle, and `silence` is a `recv_all()` modelling a
timed-out receive. `build_watchdog` wires the watchdog over a real one-way latch
and a controlled clock, so a latch a test observes is the production `SafetyLatch`,
not a stand-in.
"""

from __future__ import annotations

from backend.actuation import ManualClock, SafetyLatch
from backend.commloss import DEFAULT_COMM_TIMEOUT_SEC, CommLossWatchdog
from backend.commloss.watchdog import RecvAll, StatusBytes


def build_watchdog(
    comm_timeout_sec: float = DEFAULT_COMM_TIMEOUT_SEC,
    start: float = 0.0,
) -> tuple[CommLossWatchdog, SafetyLatch, ManualClock]:
    """Build a watchdog over a real `SafetyLatch` and a `ManualClock`.

    Args:
        comm_timeout_sec: Silence ceiling to configure.
        start: Initial clock time in seconds.

    Returns:
        (tuple) The watchdog, its shared latch, and the clock driving it.
    """
    latch = SafetyLatch()
    clock = ManualClock(start=start)
    watchdog = CommLossWatchdog(latch=latch, clock=clock, comm_timeout_sec=comm_timeout_sec)
    return watchdog, latch, clock


def status_byte(nibble: int) -> int:
    """Pack an ERR nibble into the high nibble of a Damiao status byte (`data[0]`)."""
    return nibble << 4


def frames(*status_bytes: int) -> RecvAll:
    """Return a `recv_all()` that injects these synthetic status bytes on the next cycle."""

    def _recv() -> StatusBytes:
        return list(status_bytes)

    return _recv


def silence() -> RecvAll:
    """Return a `recv_all()` modelling a timed-out receive — nothing arrived this cycle."""

    def _recv() -> StatusBytes:
        return ()

    return _recv
