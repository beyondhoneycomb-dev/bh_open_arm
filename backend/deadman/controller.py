"""The deadman controller — the one object that wires the deadman to the Wave-1 spine.

It composes the pure pieces (`RenewalReceiver`, `DeadmanMonitor`, `RearmHandshake`)
onto the two Wave-1 primitives this WP reuses rather than re-implements:

- `LeaseManager` (`backend.actuation.lease`) — the renewal timer. This controller
  renews the *same* lease the scheduler reads, so expiry has one definition.
- the scheduler's `SafetyLatch`, driven through the `LatchTarget` surface below —
  the hold. Engaging it is how expiry becomes a latch and how the scheduler's
  existing `SAFETY_LATCH_HOLD` emission is reused, not duplicated.

Expiry is judged on the server clock, and it is judged *first*, before any renewal
is evaluated: `receive_renewal` latches an already-lapsed lease before it looks at
the renewal, so a renewal that arrives after expiry can never un-expire the lease.
That ordering is the runtime teeth of "expiry = latch, no auto-resume" (U-4).

Call contract for the tick loop: call `poll` once per tick *before* the scheduler's
`tick`, so a lease that lapsed this tick is latched and the same tick emits
`SAFETY_LATCH_HOLD`. (Even without that ordering the decider still holds on the
expiry tick via its `LEASE_EXPIRED` branch, so there is never a no-command tick; the
ordering only decides whether the very first held tick is already the latch.)
"""

from __future__ import annotations

from typing import Protocol

from backend.actuation.clock import Clock
from backend.actuation.lease import LeaseManager
from backend.deadman.constants import (
    DEADMAN_LATCH_GATE_ID,
    DEADMAN_LATCH_NEW_STATE,
    DEADMAN_LATCH_PREVIOUS_STATE,
    DEADMAN_LEASE_DURATION_SEC,
    DEFAULT_MAX_LEASE_AGE_SEC,
    INITIAL_LEASE_GENERATION,
)
from backend.deadman.messages import LeaseRenewal, RenewalResult
from backend.deadman.monitor import DeadmanMonitor
from backend.deadman.rearm import RearmHandshake
from backend.deadman.receiver import RenewalReceiver
from ops.cancel.scheduler import LatchReason


class LatchTarget(Protocol):
    """The scheduler surface the deadman drives to latch, read, and clear the hold.

    `backend.actuation.scheduler.ActuationScheduler` satisfies this structurally, so
    the controller reuses the real scheduler's `SafetyLatch` and its
    `SAFETY_LATCH_HOLD` emission without importing the concrete class or standing up
    a second latch. A fault-injection double satisfies it too, for isolated tests.
    """

    def engage_safety_latch(self, reason: LatchReason) -> None:
        """Engage the one-way safety latch."""
        ...

    def acknowledge_latch(self) -> None:
        """Clear the safety latch — an operator action."""
        ...

    @property
    def latch_active(self) -> bool:
        """Whether the safety latch is currently held."""
        ...


class DeadmanController:
    """Drives lease renewal, expiry-latch, and re-arm against the reused spine."""

    def __init__(
        self,
        lease: LeaseManager,
        latch_target: LatchTarget,
        clock: Clock,
        lease_duration_sec: float = DEADMAN_LEASE_DURATION_SEC,
        max_lease_age_sec: float = DEFAULT_MAX_LEASE_AGE_SEC,
        initial_generation: int = INITIAL_LEASE_GENERATION,
    ) -> None:
        """Wire the deadman onto a reused lease and a reused scheduler latch.

        Args:
            lease: The Wave-1 `LeaseManager` the scheduler also reads. Renewed here
                so expiry has a single definition across the deadman and the spine.
            latch_target: The scheduler (or a double) whose safety latch this drives.
            clock: The server monotonic clock — the sole authority on expiry.
            lease_duration_sec: The server-clock horizon an accepted renewal grants.
                Must match the duration the reused `LeaseManager` was built with.
            max_lease_age_sec: Age past which an arrived renewal is discarded.
            initial_generation: The generation live at torque-on.
        """
        self._lease = lease
        self._latch_target = latch_target
        self._clock = clock
        self._rearm = RearmHandshake(initial_generation)
        self._receiver = RenewalReceiver(lease_duration_sec, max_lease_age_sec)
        self._monitor = DeadmanMonitor()
        self._receiver.arm(initial_generation)

    @property
    def current_generation(self) -> int:
        """The generation renewals are currently accepted for.

        Returns:
            (int) The current lease generation.
        """
        return self._rearm.current_generation

    @property
    def latched(self) -> bool:
        """Whether the deadman has latched (reads the reused scheduler latch).

        Returns:
            (bool) True once expiry has engaged the latch, until an operator re-arm.
        """
        return self._latch_target.latch_active

    @property
    def awaiting_rearm_confirmation(self) -> bool:
        """Whether a re-arm generation has been issued but not operator-confirmed.

        Returns:
            (bool) True between `request_rearm` and `confirm_rearm`.
        """
        return self._rearm.awaiting_confirmation

    def receive_renewal(self, renewal: LeaseRenewal) -> RenewalResult:
        """Judge a renewal and, if accepted, renew the reused lease.

        Expiry is latched first, on the server clock, so a renewal arriving after the
        lease has lapsed finds the deadman already latched and is refused — it cannot
        slip in before the latch and un-expire the lease.

        Args:
            renewal: The client-authored renewal.

        Returns:
            (RenewalResult) The receiver's verdict; the lease is renewed only on
            acceptance.
        """
        now = self._clock.now()
        self._latch_if_expired(now)
        result = self._receiver.receive(renewal, now, latched=self._latch_target.latch_active)
        if result.accepted:
            self._lease.renew(now)
        return result

    def poll(self) -> bool:
        """Engage the latch if the lease has lapsed. Call once per tick before `tick`.

        Returns:
            (bool) True on the tick this call engaged the latch, False otherwise.
        """
        return self._latch_if_expired(self._clock.now())

    def request_rearm(self) -> int:
        """Server step of re-arm: issue the next generation, pending operator confirm.

        Returns:
            (int) The issued, not-yet-active generation.
        """
        return self._rearm.issue()

    def confirm_rearm(self) -> int:
        """Operator step of re-arm: the sole path that clears the latch and resumes.

        Activates the issued generation, re-arms the receiver and monitor for it, and
        acknowledges the safety latch. Nothing else in this class clears the latch or
        arms a generation, which is what makes "resume requires the re-arm handshake"
        (acceptance ⑤) checkable statically.

        Returns:
            (int) The now-current generation.

        Raises:
            RearmError: If no generation was issued to confirm.
        """
        generation = self._rearm.confirm()
        self._receiver.arm(generation)
        self._monitor.arm()
        self._latch_target.acknowledge_latch()
        return generation

    def _latch_if_expired(self, now: float) -> bool:
        """Engage the latch on the expiry falling edge; report whether it fired.

        Args:
            now: The server clock reading. The only time base for the expiry
                decision — no client time is read here (acceptance ⑥).

        Returns:
            (bool) True if this call engaged the latch.
        """
        if self._monitor.observe(
            self._lease.is_expired(now), latched=self._latch_target.latch_active
        ):
            self._latch_target.engage_safety_latch(self._expiry_reason(now))
            return True
        return False

    def _expiry_reason(self, at: float) -> LatchReason:
        """Build the latch attribution for a deadman expiry.

        Args:
            at: The server clock reading to stamp the latch with.

        Returns:
            (LatchReason) A reason attributing the latch to deadman expiry.
        """
        return LatchReason(
            gate_id=DEADMAN_LATCH_GATE_ID,
            previous_state=DEADMAN_LATCH_PREVIOUS_STATE,
            new_state=DEADMAN_LATCH_NEW_STATE,
            latched_at=at,
        )
