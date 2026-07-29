"""Named constants for the WP-2C-06 reaction-path shape and static check.

Every value here is an identifier or a stated constraint — no thresholds, because this
package judges no quantity. The reaction time it once carried is not measured anywhere in
this tree; `NO_LATENCY_REASON` is why, and it is recorded into the evidence so a reader of
the artifact never has to guess whether the number is missing or hidden.
"""

from __future__ import annotations

WP_ID = "WP-2C-06"

# Why this package publishes no reaction time. The interval spans a software event —
# detection confirmed inside the control loop — and a bus event, the first byte of the
# reaction MIT frame, so it needs the same instrumentation the stop path needs (`03`
# §5.7.0: a kernel timestamp correlated to SocketCAN by SO_TIMESTAMPING, or an independent
# GPIO marker). The fitted PEAK PCAN-USB Pro FD reports hardware receive timestamps only —
# transmit timestamping off, no PTP hardware clock — and no marker is wired, so both ends
# of the interval would come from unaligned clocks. NFR-SAF-002/003/004 are decision-needed
# in any case, so there is no line the number would be judged against. The bracketed marker
# inside the value is the plan's own decision-needed token, carried as data.
NO_LATENCY_REASON = (
    "no reaction time is published: 03 §5.7.0 requires the confirm instant and the CAN frame "
    "on one trusted clock domain, and this rig's adapter has hardware receive timestamps only "
    "(transmit timestamping off, no PTP clock) with no GPIO marker wired; NFR-SAF-002/003/004 "
    "are [결정필요] and no regression gate has fixed a line to judge against"
)
