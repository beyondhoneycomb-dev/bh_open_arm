"""The latch call contract owed to the actuation scheduler.

Ownership boundary: the PHYSICAL latch executor belongs to `WP-0A-01` (the ActuationScheduler),
which does not exist yet. This package owns only the call and its ordering, so the interface is
kept as narrow as the contract requires — one method, one argument. Anything wider would be this
package guessing at a design it does not own.

Release is deliberately absent. `05` §5.2.1 states that clearing a hold latch is an explicit
re-arm handshake with a new generation id and operator intent, never an automatic consequence of
the gate later turning PASS. Offering a `release()` here would put that decision behind a call
this package has no standing to make.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LatchReason:
    """Why a hold latch was applied, and when.

    Fields match the P-0 evidence output of `05` §5.2: latch time plus `{gateId, previous state,
    new state}`. Carrying the gate identity matters because a latch with no attributable cause
    cannot be audited afterwards.
    """

    gate_id: str
    previous_state: str
    new_state: str
    latched_at: float


class ActuationScheduler(Protocol):
    """The one call this package makes into the scheduler owned by `WP-0A-01`."""

    def latch_to_hold(self, reason: LatchReason) -> None:
        """Emit the safety hold latch immediately.

        The scheduler keeps emitting the hold every tick afterwards; the latch is a hold
        emission, not a stream stop, because cutting the command stream would drop the arm
        (`00` §2-1, §2-3).

        Args:
            reason: Cause and timestamp of the latch.
        """
        ...
