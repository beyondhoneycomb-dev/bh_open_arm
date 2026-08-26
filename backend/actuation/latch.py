"""The safety latch — a hold that only an operator can clear.

Once engaged, the latch makes every subsequent tick emit SAFETY_LATCH_HOLD, and
nothing in the tick path can clear it. The only exit is `acknowledge`, an explicit
operator action (`12` FR-SAF-074 ⑤). This is what acceptance ⑤ checks: after a
latch, zero releases succeed until the operator acks — so there is deliberately no
`release()`, no timeout, no "clear once the gate passes again" path. A latch that
could clear itself would defeat its reason for existing.

The reason is typed as `ops.cancel.LatchReason` — gate id, the state either side of
the transition, and the time. A latch with no attributable cause cannot be audited
afterwards, which is the whole of why the type carries those four fields and not a
free-text string.
"""

from __future__ import annotations

from ops.cancel.scheduler import LatchReason


class SafetyLatch:
    """A one-way hold: engaged by a latch call, cleared only by operator ack."""

    def __init__(self) -> None:
        """Create a latch in the released state."""
        self._reason: LatchReason | None = None

    @property
    def is_active(self) -> bool:
        """Whether the latch is currently held.

        Returns:
            (bool) True between an engage and the operator's acknowledgement.
        """
        return self._reason is not None

    @property
    def reason(self) -> LatchReason | None:
        """The cause recorded when the latch was engaged, or None when released.

        Returns:
            (LatchReason | None) The latch reason.
        """
        return self._reason

    def engage(self, reason: LatchReason) -> None:
        """Engage the latch. Re-engaging keeps the first reason.

        Keeping the first reason matters for the audit: the cause that first put
        the arm into a latched hold is the one worth attributing, not a later
        re-assertion of the same state.

        Args:
            reason: Cause and timestamp of the latch (`ops.cancel` `LatchReason`).
        """
        if self._reason is None:
            self._reason = reason

    def acknowledge(self) -> None:
        """Clear the latch — the single legitimate release, an operator action."""
        self._reason = None
