"""Threat (b): the TX-counter watchdog — unaccounted link TX frames raise a FAULT.

A second writer is the real hazard `01` FR-SYS-007 (revised) names: it injects
commands the backend never issued, and — unlike a passive reader — it can register no
receive filter, so the RX-listener check never sees it. The only trace it leaves is
on the interface's own TX counter, which counts every frame the link transmitted
regardless of which process sent it.

So the watchdog captures the link TX packet counter at arm time as a baseline, and on
each poll compares the delta since baseline against the backend's own sent-frame
count. Agreement means every transmitted frame is ours. Any disagreement means frames
left the interface that we did not originate — a FAULT, never a WARN, and with no
auto-recovery (`IntruderMonitor` latches it).

A frame the backend sent but that never reached the wire is also a mismatch, and also
a FAULT: the contract is exact accounting, not a one-sided "too many" test.
"""

from __future__ import annotations

from backend.can.intruder.parse import parse_tx_packets
from backend.can.intruder.signals import TxMismatchFault


class TxReadError(RuntimeError):
    """The link TX counter could not be read from the supplied output.

    Raised rather than returning a zero count: an unreadable counter is a failed
    measurement, and treating it as zero would let a real mismatch pass silently.
    """


class TxCounterWatchdog:
    """Fault when link TX frames disagree with the backend's own sent-frame count.

    Args:
        iface: Interface to watch.
        baseline_tx: TX packet counter captured at arm time. Deltas are measured
            from here so the watchdog is insensitive to traffic before it armed.
    """

    def __init__(self, iface: str, baseline_tx: int) -> None:
        self.iface = iface
        self.baseline_tx = baseline_tx

    def evaluate(self, observed_tx: int, backend_sent_frames: int) -> TxMismatchFault | None:
        """Judge an observed TX counter against what the backend claims it sent.

        Args:
            observed_tx: Current link TX packet counter.
            backend_sent_frames: Frames the backend recorded sending since arm time.

        Returns:
            (TxMismatchFault | None) A FAULT when the TX delta does not equal the
            backend's sent count, else None. Never a WARN.
        """
        expected_tx = self.baseline_tx + backend_sent_frames
        if observed_tx != expected_tx:
            return TxMismatchFault(
                iface=self.iface,
                observed_tx=observed_tx,
                expected_tx=expected_tx,
            )
        return None

    def evaluate_ip_stats(
        self, ip_stats_text: str, backend_sent_frames: int
    ) -> TxMismatchFault | None:
        """Judge a captured ``ip -s link show`` against the backend's sent count.

        Args:
            ip_stats_text: Captured ``ip -s link show <iface>`` output.
            backend_sent_frames: Frames the backend recorded sending since arm time.

        Returns:
            (TxMismatchFault | None) The mismatch fault, or None.

        Raises:
            TxReadError: When the TX counter cannot be parsed from the output.
        """
        observed_tx = parse_tx_packets(ip_stats_text, self.iface)
        if observed_tx is None:
            raise TxReadError(f"no TX counter for {self.iface} in ip -s output")
        return self.evaluate(observed_tx, backend_sent_frames)
