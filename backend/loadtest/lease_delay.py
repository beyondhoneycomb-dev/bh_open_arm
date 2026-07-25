"""WS-delay injection → lease expiry → scheduler auto-hold (`CG-5-05d`, U-4 core).

The single-WS design does not remove head-of-line blocking; it folds the risk into a
stop. The dead-man is a lease the client keeps renewing over the WS, so a WS delay
means a missed renewal, a missed renewal means the lease lapses, and a lapsed lease
makes the scheduler hold. Delay does not make the stop late — delay *brings the stop
forward*. This module proves that end to end on the real objects, not a re-model:

  * the real `LeaseManager` the scheduler reads,
  * the real `DeadmanController` that renews it and latches on expiry,
  * the real `decide` function the scheduler runs each tick.

It injects a gap in the renewal stream and shows the controller latches the scheduler
into a hold, and that a fresh target sitting in the mailbox does not keep the arm live
across the lapse — expiry is judged from the clock and the last renewal alone.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.actuation.clock import ManualClock
from backend.actuation.config import FRESHNESS_WINDOW_SEC
from backend.actuation.decider import DeciderInput, decide
from backend.actuation.emissions import Emission, EmissionLabel, ReasonCode
from backend.actuation.gateway import positions_to_batch
from backend.actuation.lease import LeaseManager
from backend.actuation.mailbox import TimestampedTarget
from backend.deadman.constants import DEADMAN_LEASE_DURATION_SEC, INITIAL_LEASE_GENERATION
from backend.deadman.controller import DeadmanController
from backend.deadman.messages import LeaseRenewal
from contracts.action import RequestedPositionAction
from contracts.units import Deg, Rad
from ops.cancel.scheduler import LatchReason

# The joint width of one MIT batch (the spine's `MIT_BATCH_WIDTH`), used to build the
# hold frame and the fresh target the decider is fed.
_JOINT_COUNT = 16


class LatchRecorder:
    """A `LatchTarget` double standing in for the scheduler's `SafetyLatch`.

    `DeadmanController` drives this exactly as it drives `ActuationScheduler`
    (structural `LatchTarget`); recording the engagement is all this needs to do, so
    the lease-to-hold path can be exercised in isolation without standing up the full
    CAN spine. Engaging it is what the scheduler reads to emit `SAFETY_LATCH_HOLD`.
    """

    def __init__(self) -> None:
        """Create an unlatched recorder."""
        self._latched = False
        self._reason: LatchReason | None = None

    def engage_safety_latch(self, reason: LatchReason) -> None:
        """Engage the latch, remembering the attribution the controller passed."""
        self._latched = True
        self._reason = reason

    def acknowledge_latch(self) -> None:
        """Clear the latch — the operator ack path."""
        self._latched = False
        self._reason = None

    @property
    def latch_active(self) -> bool:
        """Whether the latch is currently engaged."""
        return self._latched

    @property
    def reason(self) -> LatchReason | None:
        """The attribution of the current latch, or None when not latched."""
        return self._reason


@dataclass(frozen=True)
class LeaseDelayResult:
    """The outcome of one WS-delay-injection run.

    Attributes:
        latched: Whether the injected delay drove the scheduler into a latched hold.
        latched_at_sec: The server-clock time the latch engaged, or None if it never
            did.
        last_renewal_at_sec: The server-clock time of the last accepted renewal.
        lease_duration_sec: The lease horizon a renewal grants.
        ticks_before_hold: How many control ticks after the last renewal the hold
            engaged.
    """

    latched: bool
    latched_at_sec: float | None
    last_renewal_at_sec: float
    lease_duration_sec: float
    ticks_before_hold: int

    @property
    def seconds_from_last_renewal_to_hold(self) -> float | None:
        """Server-clock seconds from the last renewal to the hold, or None if never held."""
        if self.latched_at_sec is None:
            return None
        return self.latched_at_sec - self.last_renewal_at_sec


def _renewal(generation: int, sequence: int, client_now: float) -> LeaseRenewal:
    """Build a renewal whose client issue time matches the server clock (zero offset)."""
    return LeaseRenewal(generation=generation, sequence=sequence, issued_mono_client=client_now)


def inject_ws_delay(
    *,
    tick_sec: float = 0.01,
    renew_every_ticks: int = 1,
    healthy_ticks: int = 5,
    delay_ticks: int = 30,
    lease_duration_sec: float = DEADMAN_LEASE_DURATION_SEC,
) -> LeaseDelayResult:
    """Renew the lease over WS, then stop (the delay), and report the auto-hold.

    The healthy phase renews on cadence and must not latch. The delay phase stops
    renewing — modelling a WS stall — and the controller is polled once per tick, as
    the tick loop does; the lease lapses `lease_duration_sec` after the last renewal
    and the poll on that tick engages the latch.

    Args:
        tick_sec: Simulated control-tick spacing.
        renew_every_ticks: Renew every N ticks during the healthy phase.
        healthy_ticks: Ticks of healthy renewal before the delay is injected.
        delay_ticks: Ticks of injected WS delay (no renewals) after the healthy phase.
        lease_duration_sec: The lease horizon; must match the controller's.

    Returns:
        (LeaseDelayResult) Whether and when the delay drove the scheduler to hold.

    Raises:
        AssertionError: If a renewal was refused during the healthy phase, or if the
            lease latched while renewals were still flowing — either would mean the
            harness was not actually exercising the delay path.
    """
    clock = ManualClock()
    lease = LeaseManager(lease_duration_sec)
    latch = LatchRecorder()
    controller = DeadmanController(
        lease=lease,
        latch_target=latch,
        clock=clock,
        lease_duration_sec=lease_duration_sec,
        initial_generation=INITIAL_LEASE_GENERATION,
    )

    sequence = 0
    last_renewal_at = clock.now()
    for tick in range(healthy_ticks):
        if tick % renew_every_ticks == 0:
            sequence += 1
            result = controller.receive_renewal(
                _renewal(INITIAL_LEASE_GENERATION, sequence, clock.now())
            )
            assert result.accepted, f"healthy renewal refused: {result.decision}"
            last_renewal_at = clock.now()
        assert not controller.poll(), "lease latched while renewals were still flowing"
        clock.advance(tick_sec)

    latched_at: float | None = None
    ticks_before_hold = 0
    for _ in range(delay_ticks):
        if controller.poll():
            latched_at = clock.now()
            break
        ticks_before_hold += 1
        clock.advance(tick_sec)

    return LeaseDelayResult(
        latched=latch.latch_active,
        latched_at_sec=latched_at,
        last_renewal_at_sec=last_renewal_at,
        lease_duration_sec=lease_duration_sec,
        ticks_before_hold=ticks_before_hold,
    )


def _fresh_target(now: float) -> TimestampedTarget:
    """A just-published, in-window target — a fresh command sitting in the mailbox."""
    request = RequestedPositionAction(values=tuple(Deg(0.0) for _ in range(_JOINT_COUNT)))
    return TimestampedTarget(request=request, published_at=now)


def decide_with_expired_lease_and_fresh_target() -> Emission:
    """Run the real decider with an expired lease AND a fresh mailbox target.

    This is the U-4 point made executable: a fresh target does not keep the arm live
    once the lease has lapsed. The decider evaluates lease expiry above the mailbox,
    so the emission is a hold attributed to the lease, not the fresh command.

    Returns:
        (Emission) The decider's emission — expected to be a lease-expired hold.
    """
    now = 1.0
    hold_batch = positions_to_batch(tuple(Rad(0.0) for _ in range(_JOINT_COUNT)))
    state = DeciderInput(
        now=now,
        safety_latched=False,
        transition_in_progress=False,
        lease_expired=True,
        mailbox_target=_fresh_target(now),
        hold_batch=hold_batch,
        freshness_window_sec=FRESHNESS_WINDOW_SEC,
        joint_limits=None,
    )
    return decide(state)


def decide_when_latched() -> Emission:
    """Run the real decider when the safety latch is engaged (post-expiry hold).

    Once `DeadmanController` has latched on expiry, the scheduler reads that latch and
    every tick emits `SAFETY_LATCH_HOLD` until an operator re-arm. This shows the
    scheduler decision the latch produces.

    Returns:
        (Emission) The decider's emission — expected to be a safety-latch hold.
    """
    now = 1.0
    hold_batch = positions_to_batch(tuple(Rad(0.0) for _ in range(_JOINT_COUNT)))
    state = DeciderInput(
        now=now,
        safety_latched=True,
        transition_in_progress=False,
        lease_expired=True,
        mailbox_target=_fresh_target(now),
        hold_batch=hold_batch,
        freshness_window_sec=FRESHNESS_WINDOW_SEC,
        joint_limits=None,
    )
    return decide(state)


# The emission labels and reason codes this WP's checks assert against, re-exported so
# a test names the scheduler's own alphabet rather than a string literal.
LEASE_EXPIRED_HOLD_LABEL = EmissionLabel.STALE_SOURCE_HOLD
LEASE_EXPIRED_HOLD_REASON = ReasonCode.LEASE_EXPIRED
SAFETY_LATCH_HOLD_LABEL = EmissionLabel.SAFETY_LATCH_HOLD
