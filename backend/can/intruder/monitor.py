"""The intruder monitor: two independent signal channels, one latched FAULT.

This is where the WARN/FAULT distinction the WP contract mandates becomes a state
machine. The monitor holds the two signals in two separate fields — a
`ListenerWarning` and a `TxMismatchFault` — never a single "alarm". Its derived
state is FAULT if a fault is latched, else WARN if a warning stands, else OK; a
warning can never escalate itself to FAULT, and a fault is never downgraded to a
warning.

Two invariants the WP acceptance turns on:

- **FAULT is terminal and self-recovery does not exist.** There is no code path in
  this class that transitions a latched fault back to OK on its own. `recovery_attempts`
  is exposed and is only ever 0, because the monitor never attempts recovery — the
  absence of the mechanism is the guarantee (acceptance ⑤). The single exit is
  `manual_clear`, which an operator calls explicitly with an acknowledgement.
- **WARN does not block; FAULT does.** `may_proceed` is true in OK and WARN and
  false in FAULT, so a passive reader (WARN) lets the user continue while a second
  writer (FAULT) stops the line.
"""

from __future__ import annotations

from enum import Enum

from backend.can.intruder.listener import RxListenerCheck
from backend.can.intruder.signals import ListenerWarning, TxMismatchFault
from backend.can.intruder.txwatch import TxCounterWatchdog


class MonitorState(Enum):
    """Derived state of the monitor. FAULT dominates WARN dominates OK."""

    OK = "OK"
    WARN = "WARN"
    FAULT = "FAULT"


class OperatorAckError(RuntimeError):
    """A manual FAULT clear was attempted without a non-empty operator acknowledgement."""


class IntruderMonitor:
    """Run the RX-listener and TX-counter checks and latch their signals.

    The monitor owns one `RxListenerCheck` and one `TxCounterWatchdog` for a single
    interface. Its two `observe_*` methods feed captured text to those checks and
    record whatever they return. The fault, once latched, stays until `manual_clear`.

    Args:
        listener_check: The RX-listener excess check (WARN source).
        tx_watchdog: The TX-counter watchdog (FAULT source).
    """

    def __init__(self, listener_check: RxListenerCheck, tx_watchdog: TxCounterWatchdog) -> None:
        self.listener_check = listener_check
        self.tx_watchdog = tx_watchdog
        self._warning: ListenerWarning | None = None
        self._fault: TxMismatchFault | None = None
        # Only ever 0. Its constancy is acceptance ⑤: the monitor attempts no
        # recovery, so a caller can assert this after any number of polls.
        self.recovery_attempts = 0
        self.manual_clears = 0

    @property
    def state(self) -> MonitorState:
        """Return the derived state: FAULT if latched, else WARN if standing, else OK."""
        if self._fault is not None:
            return MonitorState.FAULT
        if self._warning is not None:
            return MonitorState.WARN
        return MonitorState.OK

    @property
    def warning(self) -> ListenerWarning | None:
        """Return the standing RX-listener warning, if any (kept apart from the fault)."""
        return self._warning

    @property
    def fault(self) -> TxMismatchFault | None:
        """Return the latched TX-mismatch fault, if any (kept apart from the warning)."""
        return self._fault

    @property
    def may_proceed(self) -> bool:
        """Report whether the line may proceed: true in OK and WARN, false in FAULT."""
        return self._fault is None

    def observe_listeners(self, rcvlist_text: str) -> ListenerWarning | None:
        """Feed a captured rcvlist to the RX check and record any warning.

        A warning updates the WARN channel only; it never sets or clears a fault, so
        the RX side cannot escalate to FAULT no matter what it sees.

        Args:
            rcvlist_text: Captured ``/proc/net/can/rcvlist_all`` contents.

        Returns:
            (ListenerWarning | None) The warning this observation produced.
        """
        self._warning = self.listener_check.evaluate_rcvlist(rcvlist_text)
        return self._warning

    def observe_tx(self, ip_stats_text: str, backend_sent_frames: int) -> TxMismatchFault | None:
        """Feed captured link stats to the TX watchdog and latch any fault.

        Once a fault is latched it is never overwritten with None: a later clean poll
        does not clear a fault (only `manual_clear` does), because a second writer that
        stops sending has still already injected commands.

        Args:
            ip_stats_text: Captured ``ip -s link show <iface>`` output.
            backend_sent_frames: Frames the backend recorded sending since arm time.

        Returns:
            (TxMismatchFault | None) The fault this observation produced, if any.
        """
        fault = self.tx_watchdog.evaluate_ip_stats(ip_stats_text, backend_sent_frames)
        if fault is not None:
            self._fault = fault
        return fault

    def manual_clear(self, operator_ack: str) -> None:
        """Clear a latched fault, but only on an explicit operator acknowledgement.

        This is the sole exit from FAULT, and it is not automatic: it exists so that
        `recovery_attempts` can stay 0 while still giving an operator a deliberate way
        out. An empty acknowledgement is refused.

        Args:
            operator_ack: Non-empty acknowledgement string identifying the operator.

        Raises:
            OperatorAckError: When the acknowledgement is empty or blank.
        """
        if not operator_ack.strip():
            raise OperatorAckError("manual clear requires a non-empty operator acknowledgement")
        self._fault = None
        self.manual_clears += 1
