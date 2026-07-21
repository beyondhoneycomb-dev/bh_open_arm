"""Frozen link-verification thresholds from `01` FR-SYS-006 / FR-SYS-011.

These are the exact values `Robot.connect()` refuses to start without: a CAN-FD link at
1 Mbit/s nominal, 5 Mbit/s data, in the `ERROR-ACTIVE` bus state. `BUS-OFF` is named
separately because it is the specific failed state the check must reject, not a generic
"not active". `txqueuelen` is a recommendation (FR-SYS-011, priority S), never a refusal
criterion, so it lives here for the setup artifact while the validator ignores it.
"""

from __future__ import annotations

# FR-SYS-006 startup-refusal criteria: the link must be CAN-FD, 1 Mbit/s arbitration,
# 5 Mbit/s data, error-active. Any deviation refuses startup.
REQUIRED_FD = True
REQUIRED_BITRATE = 1_000_000
REQUIRED_DBITRATE = 5_000_000
ACTIVE_STATE = "ERROR-ACTIVE"
BUS_OFF_STATE = "BUS-OFF"

# FR-SYS-011 (priority S): the kernel default is 10; the recommendation is 1000. Carried
# in the setup artifact and surfaced as a verdict advisory, but never a refusal.
DEFAULT_TXQUEUELEN = 10
RECOMMENDED_TXQUEUELEN = 1000
