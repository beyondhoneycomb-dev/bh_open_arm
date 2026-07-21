"""Mode transition as an atomic producer swap that never stops the scheduler.

The rule (`02a` §3.1 ④): a mode change does not pause the CAN stream — cutting it
would drop the arm (`12` NFR-SAF-009). Instead the *producer* is swapped under a
still-running scheduler. The procedure is: prepare the new producer, perform a
single atomic swap, then join the old one.

"Atomic" here is a single reference reassignment (`_active`), which CPython
executes indivisibly, so the tick decider never observes a half-swapped producer.
The window between `begin` and `commit` — where the new producer is prepared and
the old one is being wound down — is bracketed by `in_progress`, and every tick in
that window emits MODE_TRANSITION_HOLD. That is why acceptance ② sees no empty
ticks and no non-hold gap other than MODE_TRANSITION_HOLD: the scheduler holds
across the swap rather than skipping.
"""

from __future__ import annotations

from backend.actuation.producer import Producer


class ModeTransition:
    """Owns which producer is active and the swap that changes it.

    Ownership: the scheduler holds exactly one of these. Producers are swapped
    through it; the scheduler reads `in_progress` each tick to decide whether to
    hold.
    """

    def __init__(self, active: Producer) -> None:
        """Start bound to an initial active producer.

        Args:
            active: The producer live at torque-on.
        """
        self._active = active
        self._pending: Producer | None = None
        self._in_progress = False

    @property
    def in_progress(self) -> bool:
        """Whether a swap is currently bracketed (begun, not yet committed).

        Returns:
            (bool) True between `begin` and `commit`.
        """
        return self._in_progress

    @property
    def active_id(self) -> str:
        """Identity of the currently active producer.

        Returns:
            (str) The active producer's id.
        """
        return self._active.producer_id

    def begin(self, incoming: Producer) -> None:
        """Open a transition to a prepared incoming producer.

        Ticks emit MODE_TRANSITION_HOLD until `commit`. Beginning a transition
        while one is already open is a programming error, because two overlapping
        swaps would make "which producer is next" ambiguous.

        Args:
            incoming: The already-prepared new producer.

        Raises:
            RuntimeError: If a transition is already in progress.
        """
        if self._in_progress:
            raise RuntimeError("a mode transition is already in progress")
        self._pending = incoming
        self._in_progress = True

    def commit(self) -> Producer:
        """Perform the atomic swap and hand back the outgoing producer to join.

        The swap is the single reassignment of `_active`; the caller joins the
        returned producer afterwards, so joining never races the swap.

        Returns:
            (Producer) The producer that was just swapped out, for the caller to
            join.

        Raises:
            RuntimeError: If no transition is in progress.
        """
        if not self._in_progress or self._pending is None:
            raise RuntimeError("commit called with no transition in progress")
        outgoing = self._active
        self._active = self._pending
        self._pending = None
        self._in_progress = False
        return outgoing
