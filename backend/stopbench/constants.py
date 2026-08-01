"""Named constants for the WP-2A-06 stop-path shape and static check.

Every value here is an identifier or a stated constraint — no thresholds, because this
package judges no quantity. No stop-path latency is measured anywhere in this tree;
`NO_LATENCY_REASON` is why, and it is recorded into the evidence so a reader of the
artifact never has to guess whether the number is missing or hidden.
"""

from __future__ import annotations

WP_ID = "WP-2A-06"

# Why this package publishes no stop latency. `03` §5.7.0 allows exactly two sources for
# the release instant — a kernel timestamp correlated to SocketCAN by SO_TIMESTAMPING, or
# an independent GPIO/logic-analyser marker — and the fitted PEAK PCAN-USB Pro FD reports
# hardware receive timestamps only: transmit timestamping off, no PTP hardware clock. The
# release instant would therefore come from a software clock, whose error against the
# other end of the interval is milliseconds, and the 20 ms it would be compared to is
# itself an [unconfirmed] target (`04` NFR-MAN-002), not a measurement. Subtracting two
# unaligned clocks is the forgery §5.7.0 rules out, so the measurement is out of scope
# here rather than approximated.
NO_LATENCY_REASON = (
    "no stop-path latency is published: 03 §5.7.0 requires the release instant and the CAN "
    "frame on one trusted clock domain, and this rig's adapter has hardware receive "
    "timestamps only (transmit timestamping off, no PTP clock) with no GPIO marker wired, "
    "so the release instant exists only on a software clock; 04 NFR-MAN-002's 20 ms is an "
    "[unconfirmed] target in any case. Measurement is owned by PG-STOP-001 (WP-1-05)"
)
