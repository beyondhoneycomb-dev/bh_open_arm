"""Threat (a): the RX-listener excess check — extra receivers raise a WARN.

`01` FR-SYS-007 (revised) establishes that a passive reader steals nothing: the CAN
core fans every matching frame out to all bound sockets, so a ``candump`` copies our
traffic without depriving us of it. An extra listener is therefore reported, not
blocked — the operator may knowingly have one open. This check owns only that WARN;
it never emits a FAULT, and it is by construction blind to a writer that registers no
receive filter (that is the TX watchdog's job, and acceptance ④ proves the two do not
overlap).

"Excess" is measured against the count this process legitimately owns, not against
zero: our own reader and writer sockets each register a receive-all filter, so their
rows are expected and only rows beyond them are the warning.
"""

from __future__ import annotations

from backend.can.intruder.parse import listeners_for
from backend.can.intruder.signals import ListenerWarning


class RxListenerCheck:
    """Raise a WARN when an interface carries more listeners than we registered.

    Args:
        iface: Interface to watch.
        expected_own_listeners: Receive-all registrations this process owns (its
            reader and writer sockets). Rows beyond this count are the excess.
    """

    def __init__(self, iface: str, expected_own_listeners: int) -> None:
        self.iface = iface
        self.expected_own_listeners = expected_own_listeners

    def evaluate(self, observed_listeners: int) -> ListenerWarning | None:
        """Judge a listener count, returning a WARN only on genuine excess.

        Args:
            observed_listeners: Total receive-all registrations seen for the iface.

        Returns:
            (ListenerWarning | None) A WARN when observed exceeds our own count,
            else None. Never a FAULT.
        """
        if observed_listeners > self.expected_own_listeners:
            return ListenerWarning(
                iface=self.iface,
                observed_listeners=observed_listeners,
                expected_listeners=self.expected_own_listeners,
            )
        return None

    def evaluate_rcvlist(self, rcvlist_text: str) -> ListenerWarning | None:
        """Judge a captured ``/proc/net/can/rcvlist_all`` for this interface.

        Args:
            rcvlist_text: Captured proc-file contents.

        Returns:
            (ListenerWarning | None) The excess warning, or None.
        """
        return self.evaluate(listeners_for(rcvlist_text, self.iface))
