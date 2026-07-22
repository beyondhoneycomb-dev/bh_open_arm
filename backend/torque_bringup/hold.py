"""SAFE_HOLD is a gravity-comp hold, and the scheduler proves it holds under fault.

Two things live here. First, `assert_safe_hold` — the impl check that a hold frame is a
gravity-comp present-pose hold and not a torque-0 limp command. `01` §4.1 is explicit that
SAFE_HOLD is *not* torque 0: a QDD joint is backdrivable and has no brake, so a hold that
zeroes stiffness lets the arm fall. The frame that holds is a MIT position hold with kp > 0
— the motor generates the holding torque through its position loop — so a frame with
kp <= 0 is a drop dressed as a hold, and acceptance ⑫ refuses it.

Second, the hold demonstrations. The lease-expiry-forces-a-hold logic already lives in the
actuation spine's decider (a lapsed deadman is priority 2, above any producer); this WP
does not reimplement it, it *drives* the spine offline and measures the properties the
acceptance gates name:

  * hold maintenance (⑤): with no producer publishing, every tick emits a hold, the hold
    frame never drifts, exactly one CAN frame goes out per tick (⑧), and the send interval
    stays under the RID-9 no-send margin (②, `12` NFR-SAF-007).
  * lease expiry (⑦): renewal stops, and the very tick the lease lapses emits the hold —
    zero delay ticks, decided from the clock alone, independent of the mailbox.

Both run on the fake CAN writer and manual clock (`AI-offline`). The *physical* joint
drift and the real stop frame are deferred to a real fixture.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.actuation import (
    ActuationScheduler,
    EmissionLabel,
    FakeCanWriter,
    LeaseManager,
    MailboxProducer,
    ManualClock,
    ReasonCode,
    TargetMailbox,
    TickTrace,
)
from backend.actuation.config import (
    FRESHNESS_WINDOW_SEC,
    LEASE_DURATION_SEC,
    RID9_NO_SEND_MARGIN_SEC,
    TICK_INTERVAL_SEC,
)
from contracts.action import ExecutedMitCommand, RequestedPositionAction
from contracts.units import Deg, Rad


class SafeHoldViolationError(Exception):
    """Raised when a frame offered as a SAFE_HOLD is actually a torque-0 command.

    A hold with zero stiffness cannot hold a backdrivable brakeless arm; it is a drop.
    Raising rather than sending is the whole point (`01` §4.1, `12` NFR-SAF-009).
    """


def assert_safe_hold(hold_batch: tuple[ExecutedMitCommand, ...]) -> None:
    """Refuse a hold frame that would let a brakeless arm fall (acceptance ⑫).

    A SAFE_HOLD is a gravity-comp present-pose hold: the MIT position loop holds the pose,
    which requires a non-zero stiffness. A frame with kp <= 0 commands no restoring torque
    and drops the arm, so it is not a SAFE_HOLD however it is labelled.

    Args:
        hold_batch: The MIT frame offered as a hold.

    Raises:
        SafeHoldViolationError: If any joint's stiffness is zero or negative.
    """
    for index, command in enumerate(hold_batch):
        if command.kp <= 0.0:
            raise SafeHoldViolationError(
                f"joint {index}: SAFE_HOLD has kp={command.kp} <= 0; a zero-stiffness frame is a "
                "torque-0 limp command that drops a brakeless arm — SAFE_HOLD is a gravity-comp "
                "hold, not torque 0 (01 §4.1, 12 NFR-SAF-009, acceptance ⑫)"
            )


@dataclass
class _HeldSpine:
    """The actuation spine armed at torque-on, holding a present pose, on a fake bus."""

    scheduler: ActuationScheduler
    clock: ManualClock
    writer: FakeCanWriter
    lease: LeaseManager
    mailbox: TargetMailbox
    producer: MailboxProducer
    trace: TickTrace
    tick_interval_sec: float


def _build_held_spine(
    present: tuple[Rad, ...],
    lease_duration_sec: float,
    tick_interval_sec: float,
) -> _HeldSpine:
    """Stand up the actuation spine holding a present pose, renewed live at torque-on.

    Args:
        present: The present-pose hold the spine parks at, radians per joint.
        lease_duration_sec: The deadman lease duration.
        tick_interval_sec: How far the manual clock advances per tick.

    Returns:
        (_HeldSpine) The wired spine plus the levers to drive and observe it.
    """
    clock = ManualClock()
    writer = FakeCanWriter()
    mailbox = TargetMailbox()
    lease = LeaseManager(lease_duration_sec)
    producer = MailboxProducer("wp-1-05-torque-on", mailbox, clock)
    trace = TickTrace()
    scheduler = ActuationScheduler(
        can_writer=writer,
        mailbox=mailbox,
        clock=clock,
        lease=lease,
        initial_producer=producer,
        initial_hold_positions=present,
        trace=trace,
        freshness_window_sec=FRESHNESS_WINDOW_SEC,
    )
    # Live at torque-on: without an initial renewal the first tick reads an un-renewed
    # (expired) lease and holds. A guarded torque-ON session is armed.
    lease.renew(clock.now())
    return _HeldSpine(
        scheduler=scheduler,
        clock=clock,
        writer=writer,
        lease=lease,
        mailbox=mailbox,
        producer=producer,
        trace=trace,
        tick_interval_sec=tick_interval_sec,
    )


@dataclass(frozen=True)
class HoldMaintenanceReport:
    """The measured properties of a producer-less hold (acceptance ⑤⑧, ② send period).

    Attributes:
        ticks: How many ticks were driven.
        all_holds: Whether every tick emitted a hold (no ACCEPTED_TARGET slipped through).
        commanded_drift_rad: The largest change in any commanded hold angle across the
            run. The commanded frame never moves, so this is 0.0 offline; the physical
            joint drift is deferred.
        frames_written: Total CAN frames sent — one per tick under the single-writer
            invariant, so this equals `ticks`.
        max_send_interval_sec: The longest gap between two consecutive sends.
        rid9_no_send_margin_sec: The RID-9 no-send ceiling the interval must stay under.
    """

    ticks: int
    all_holds: bool
    commanded_drift_rad: float
    frames_written: int
    max_send_interval_sec: float
    rid9_no_send_margin_sec: float

    @property
    def send_period_under_margin(self) -> bool:
        """Whether the Cat-2 hold send period stayed under the RID-9 no-send margin.

        Returns:
            (bool) True when the longest send interval is strictly under the margin.
        """
        return self.max_send_interval_sec < self.rid9_no_send_margin_sec


def verify_hold_maintenance(
    present: tuple[Rad, ...],
    ticks: int,
    lease_duration_sec: float = LEASE_DURATION_SEC,
    tick_interval_sec: float = TICK_INTERVAL_SEC,
) -> HoldMaintenanceReport:
    """Drive a producer-less held spine and measure that it holds every tick (⑤⑧②).

    The deadman is renewed each tick (the operator is present) but no producer publishes,
    so every tick is a STALE_SOURCE_HOLD on an empty mailbox. The hold frame never moves,
    exactly one frame is sent per tick, and the send interval stays under the RID-9 margin.

    Args:
        present: The present-pose hold the spine parks at.
        ticks: How many ticks to drive.
        lease_duration_sec: The deadman lease duration.
        tick_interval_sec: How far the clock advances per tick.

    Returns:
        (HoldMaintenanceReport) The measured hold properties.
    """
    spine = _build_held_spine(present, lease_duration_sec, tick_interval_sec)
    all_holds = True
    for _ in range(ticks):
        spine.clock.advance(tick_interval_sec)
        spine.scheduler.renew_lease()
        emission = spine.scheduler.tick()
        if not emission.is_hold:
            all_holds = False
    return HoldMaintenanceReport(
        ticks=ticks,
        all_holds=all_holds,
        commanded_drift_rad=_commanded_drift(spine.trace),
        frames_written=spine.writer.write_count,
        max_send_interval_sec=spine.trace.max_send_interval(),
        rid9_no_send_margin_sec=RID9_NO_SEND_MARGIN_SEC,
    )


def _commanded_drift(trace: TickTrace) -> float:
    """Return the largest change in any commanded hold angle across the trace.

    Args:
        trace: The per-tick trace of what was written.

    Returns:
        (float) The maximum absolute per-joint angle change between the first frame and
        any later frame, radians; 0.0 when nothing moved.
    """
    if not trace.entries:
        return 0.0
    first = trace.entries[0].batch
    drift = 0.0
    for entry in trace.entries[1:]:
        for base, command in zip(first, entry.batch, strict=True):
            drift = max(drift, abs(command.q.value - base.q.value))
    return drift


@dataclass(frozen=True)
class LeaseExpiryReport:
    """The measured lease-expiry-forces-a-hold behaviour (acceptance ⑦).

    Attributes:
        first_expiry_condition_tick: The tick index at which the lease first lapsed by the
            clock alone.
        first_hold_tick: The tick index at which the emission first became a LEASE_EXPIRED
            hold.
        holds_after_expiry: Whether every tick from expiry onward was a hold.
    """

    first_expiry_condition_tick: int
    first_hold_tick: int
    holds_after_expiry: bool

    @property
    def delay_ticks(self) -> int:
        """Ticks between the lease lapsing and the hold being emitted.

        Returns:
            (int) Zero when the hold is emitted on the very tick the lease lapses, which
            is the property acceptance ⑦ requires.
        """
        return self.first_hold_tick - self.first_expiry_condition_tick


def verify_lease_expiry(
    present: tuple[Rad, ...],
    warmup_ticks: int,
    coast_ticks: int,
    lease_duration_sec: float = LEASE_DURATION_SEC,
    tick_interval_sec: float = TICK_INTERVAL_SEC,
) -> LeaseExpiryReport:
    """Renew for a while, then stop, and show the lapse tick emits the hold (⑦).

    During warmup the deadman is renewed and a fresh target is published, so the arm is
    live (ACCEPTED_TARGET). Then renewal stops while the clock keeps advancing; the tick
    the lease lapses by the clock is the tick the hold is emitted — zero delay, decided
    from the clock alone even though a fresh target still sits in the mailbox.

    Args:
        present: The present-pose hold the spine parks at.
        warmup_ticks: Live ticks before renewal stops.
        coast_ticks: Ticks driven after renewal stops.
        lease_duration_sec: The deadman lease duration.
        tick_interval_sec: How far the clock advances per tick.

    Returns:
        (LeaseExpiryReport) When the lease lapsed and when the hold appeared.
    """
    spine = _build_held_spine(present, lease_duration_sec, tick_interval_sec)
    request = RequestedPositionAction(values=tuple(Deg(0.0) for _ in present))

    last_renewed_at = spine.clock.now()
    for _ in range(warmup_ticks):
        spine.clock.advance(tick_interval_sec)
        spine.scheduler.renew_lease()
        last_renewed_at = spine.clock.now()
        spine.producer.publish(request)
        spine.scheduler.tick()

    first_expiry_condition_tick = -1
    first_hold_tick = -1
    holds_after_expiry = True
    for offset in range(coast_ticks):
        spine.clock.advance(tick_interval_sec)
        # Keep a fresh target in the mailbox but never renew: expiry must win over a live
        # producer, which is the independence property (04 FR-MAN-050).
        spine.producer.publish(request)
        now = spine.clock.now()
        lapsed = (now - last_renewed_at) > lease_duration_sec
        if lapsed and first_expiry_condition_tick < 0:
            first_expiry_condition_tick = offset
        emission = spine.scheduler.tick()
        is_lease_hold = (
            emission.label is EmissionLabel.STALE_SOURCE_HOLD
            and emission.reason is ReasonCode.LEASE_EXPIRED
        )
        if is_lease_hold and first_hold_tick < 0:
            first_hold_tick = offset
        if first_expiry_condition_tick >= 0 and offset >= first_expiry_condition_tick:
            holds_after_expiry = holds_after_expiry and emission.is_hold

    return LeaseExpiryReport(
        first_expiry_condition_tick=first_expiry_condition_tick,
        first_hold_tick=first_hold_tick,
        holds_after_expiry=holds_after_expiry,
    )
