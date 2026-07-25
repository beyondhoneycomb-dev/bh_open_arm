"""Admin forced release — safe HOLD first, then fence the prior holder (`FR-OPS-076`).

`FR-OPS-076` gives an admin the authority to take command away from the current L2
holder, but pins the ordering: the arm must transition to a **safe HOLD before the
release**, never after. `FR-OPS-091` adds the fence: the forced release increments
`lease_generation` so the prior holder's in-flight or resent commands — which may
still be on the wire — are invalidated (`CG-5-08c`).

The generation is not a second counter this module owns. It is the *one* deadman
lease's generation, advanced through the deadman's own re-arm handshake
(`request_rearm` then `confirm_rearm`). That handshake's `confirm` step also
acknowledges the safety latch (its normal job is to *resume* from a latch), so a
forced release re-asserts the hold afterwards: a forced release must leave the arm
latched, not resumed. The recorded event order proves HOLD precedes RELEASE
regardless of that internal clear/re-assert.

Only an admin may force-release; an operator or observer attempting it is refused
(this is one of the command paths `FR-OPS-077` closes to an observer).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.deadman.controller import DeadmanController, LatchTarget
from backend.security.control_lock import CommandSourceLock
from contracts.ws import WsRole
from ops.cancel.scheduler import LatchReason


class ForcedReleaseError(RuntimeError):
    """Raised when a non-admin attempts a forced release (`FR-OPS-076`)."""


class ForceReleaseStep(Enum):
    """The ordered steps of a forced release, recorded so the ordering is checkable.

    The sequence is the contract: HOLD is engaged first, the lease generation is
    advanced (fencing the prior holder), the hold is re-asserted because the re-arm
    handshake's confirm cleared it, and only then is the L2 lock released.
    """

    HOLD_ENGAGED = "hold_engaged"
    GENERATION_INCREMENTED = "generation_incremented"
    HOLD_REASSERTED = "hold_reasserted"
    LOCK_RELEASED = "lock_released"


@dataclass(frozen=True)
class ForceReleaseOutcome:
    """The result of a forced release.

    Attributes:
        steps: The steps in the exact order they happened; HOLD_ENGAGED is first and
            LOCK_RELEASED is last, which is the `CG-5-08c` "safe HOLD before release"
            evidence.
        previous_generation: The lease generation before the release.
        new_generation: The lease generation after — strictly greater, the fence that
            invalidates the prior holder's stale-generation commands.
        held_before_release: Whether the safety latch was already engaged at the
            moment before the L2 lock was released (must be True).
        latched_after: Whether the arm is left latched after the release (a forced
            release leaves a safe HOLD that resumes only through a new re-arm).
    """

    steps: tuple[ForceReleaseStep, ...]
    previous_generation: int
    new_generation: int
    held_before_release: bool
    latched_after: bool


class ForcedRelease:
    """Executes a `FR-OPS-076` forced release against the one deadman lease and L2 lock.

    Ownership: drives the reused deadman controller (generation + latch), the reused
    scheduler latch target (the HOLD), and the L2 command-source lock (the release).
    It owns no lease and no generation of its own — the generation it increments is
    the deadman's, advanced through the deadman's public re-arm handshake.
    """

    def __init__(
        self,
        controller: DeadmanController,
        latch_target: LatchTarget,
        command_lock: CommandSourceLock,
    ) -> None:
        """Wire the forced release onto the reused deadman, latch, and L2 lock.

        Args:
            controller: The U-4 deadman controller whose generation is advanced.
            latch_target: The scheduler latch (or double) the HOLD is engaged on —
                the same latch the deadman's expiry engages.
            command_lock: The L2 command-source lock to release.
        """
        self._controller = controller
        self._latch_target = latch_target
        self._command_lock = command_lock

    def execute(self, role: WsRole, reason: LatchReason) -> ForceReleaseOutcome:
        """Force-release: HOLD, fence the generation, re-assert HOLD, release L2.

        Args:
            role: The requesting session's role; only admin may force-release.
            reason: Cause and timestamp attributed to the safety HOLD.

        Returns:
            (ForceReleaseOutcome) The ordered steps and the generation fence.

        Raises:
            ForcedReleaseError: If the requester is not an admin.
        """
        if role is not WsRole.ADMIN:
            raise ForcedReleaseError(
                f"forced release requires the {WsRole.ADMIN.value!r} role; {role.value!r} refused"
            )

        steps: list[ForceReleaseStep] = []
        previous_generation = self._controller.current_generation

        # 1. Safe HOLD FIRST — before anything is released (`FR-OPS-076`).
        self._latch_target.engage_safety_latch(reason)
        steps.append(ForceReleaseStep.HOLD_ENGAGED)
        held_before_release = self._latch_target.latch_active

        # 2. Advance the ONE lease's generation through its own re-arm handshake,
        #    fencing the prior holder. `confirm_rearm` also acknowledges the latch
        #    (its resume role), which is why step 3 re-asserts the HOLD.
        self._controller.request_rearm()
        new_generation = self._controller.confirm_rearm()
        steps.append(ForceReleaseStep.GENERATION_INCREMENTED)

        # 3. Re-assert the HOLD: a forced release must leave the arm latched, not
        #    resumed, so a new holder can only take control through a fresh re-arm.
        self._latch_target.engage_safety_latch(reason)
        steps.append(ForceReleaseStep.HOLD_REASSERTED)

        # 4. Release L2 — last, with the HOLD already in place.
        self._command_lock.release()
        steps.append(ForceReleaseStep.LOCK_RELEASED)

        return ForceReleaseOutcome(
            steps=tuple(steps),
            previous_generation=previous_generation,
            new_generation=new_generation,
            held_before_release=held_before_release,
            latched_after=self._latch_target.latch_active,
        )
