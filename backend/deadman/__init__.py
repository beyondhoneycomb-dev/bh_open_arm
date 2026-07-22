"""WP-2A-02 — the deadman lease: renewal, expiry-as-latch, and the re-arm handshake (U-4).

The deadman is a renewal lease, not a held button: control is kept alive by renewals
that must arrive before the lease expires, and the absence of renewal — for any
reason, including the operator's process dying — expires it. This package adds, on
top of the Wave-1 spine it reuses, the four things that make expiry safe:

- a wire contract (`LeaseRenewal`) and a server-held record (`DeadmanLease`) that put
  every expiry decision on the server clock and keep the client clock to age only;
- a `RenewalReceiver` that rejects replays and stale/forged generations and discards
  renewals delayed past `max_lease_age`;
- a `DeadmanMonitor` + `DeadmanController` that turn expiry into a one-way SAFETY
  latch — reusing the scheduler's `SafetyLatch` and `SAFETY_LATCH_HOLD` emission —
  so a renewal arriving after expiry cannot resume motion;
- a `RearmHandshake`: the sole, server-issued, operator-confirmed path back to live.

What it reuses rather than re-implements: `LeaseManager` (the renewal timer) and the
scheduler's latch and hold, both from `backend.actuation`. This package renews the
same lease the scheduler reads and engages the same latch it emits, so the deadman
has one definition of expiry and one hold, not two.
"""

from __future__ import annotations

from backend.deadman.age_filter import ClientClockOffset
from backend.deadman.constants import (
    DEADMAN_LEASE_DURATION_SEC,
    DEFAULT_MAX_LEASE_AGE_SEC,
    INITIAL_LEASE_GENERATION,
)
from backend.deadman.controller import DeadmanController, LatchTarget
from backend.deadman.intake import IntakeClass, RenewalIntake
from backend.deadman.messages import (
    DeadmanLease,
    LeaseRenewal,
    RenewalDecision,
    RenewalResult,
)
from backend.deadman.monitor import DeadmanMonitor
from backend.deadman.rearm import RearmError, RearmHandshake
from backend.deadman.receiver import RenewalReceiver
from backend.deadman.reverify import (
    CANDUMP_CAPTURE_ENV_VAR,
    FrameKind,
    ObservedFrame,
    ReverifyReport,
    reverify_expiry_stop,
    reverify_from_capture,
)

__all__ = [
    "CANDUMP_CAPTURE_ENV_VAR",
    "DEADMAN_LEASE_DURATION_SEC",
    "DEFAULT_MAX_LEASE_AGE_SEC",
    "INITIAL_LEASE_GENERATION",
    "ClientClockOffset",
    "DeadmanController",
    "DeadmanLease",
    "DeadmanMonitor",
    "FrameKind",
    "IntakeClass",
    "LatchTarget",
    "LeaseRenewal",
    "ObservedFrame",
    "RearmError",
    "RearmHandshake",
    "RenewalDecision",
    "RenewalIntake",
    "RenewalReceiver",
    "RenewalResult",
    "ReverifyReport",
    "reverify_expiry_stop",
    "reverify_from_capture",
]
