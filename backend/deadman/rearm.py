"""The re-arm handshake — the only way a latched deadman resumes.

Once the lease has latched, no renewal resumes motion (that is what "latch" means).
Resume takes two deliberate steps, in order, and this class holds that state machine:

1. **Issue** — the *server* mints the next `lease_generation`. A generation is never
   asserted by a client; issuance lives here, on the server, so a client cannot talk
   its way back to a live arm by claiming a higher generation.
2. **Confirm** — the *operator* affirms intent. Only after confirmation does the new
   generation become the one the receiver accepts.

Issuing without confirming resumes nothing: a stuck or hostile issue path cannot,
on its own, re-arm the deadman. This class carries only the generation bookkeeping;
clearing the actual `SafetyLatch` and re-arming the receiver and monitor is the
controller's job, done exactly once, at confirmation.
"""

from __future__ import annotations


class RearmError(RuntimeError):
    """Raised on an out-of-order re-arm step (confirming with nothing issued)."""


class RearmHandshake:
    """A two-step generation machine: issue (server) then confirm (operator)."""

    def __init__(self, initial_generation: int) -> None:
        """Start armed at `initial_generation` with no re-arm pending.

        The initial generation is live from torque-on: the first take of the deadman
        is a renewal, not a re-arm, because there is no prior latch to clear.

        Args:
            initial_generation: The generation live at torque-on.
        """
        self._current_generation = initial_generation
        self._pending_generation: int | None = None

    @property
    def current_generation(self) -> int:
        """The generation the receiver should accept renewals for.

        Returns:
            (int) The current generation.
        """
        return self._current_generation

    @property
    def awaiting_confirmation(self) -> bool:
        """Whether a generation has been issued but not yet operator-confirmed.

        Returns:
            (bool) True between `issue` and `confirm`.
        """
        return self._pending_generation is not None

    def issue(self) -> int:
        """Server step: mint the next generation, pending operator confirmation.

        Re-issuing before a confirmation overwrites the pending generation rather
        than stacking — the server offering a fresh re-arm supersedes an unconfirmed
        one, and only a confirmation ever advances the current generation.

        Returns:
            (int) The newly issued, not-yet-active generation.
        """
        self._pending_generation = self._current_generation + 1
        return self._pending_generation

    def confirm(self) -> int:
        """Operator step: activate the issued generation.

        Returns:
            (int) The now-current generation.

        Raises:
            RearmError: If no generation has been issued to confirm — resume must
                not proceed on a confirmation that answers no offer.
        """
        if self._pending_generation is None:
            raise RearmError("confirm called with no generation issued")
        self._current_generation = self._pending_generation
        self._pending_generation = None
        return self._current_generation
