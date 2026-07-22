"""A jog-driven scheduler bench, wired entirely from Wave-1 primitives.

The two behavioural acceptance gates for `WP-2A-01` — a step emitted as a
trajectory (②) and a producer swap that interrupts no tick (③) — are properties of
how the jog producer feeds the *real* scheduler, so they must be observed through
it, not through a mock. This bench wires the actual `ActuationScheduler` around a
`JointJogProducer` using the Wave-1 fake CAN backend and controlled clock; nothing
here re-implements a scheduler, mailbox, lease, or swap — they are imported and
composed, and only the producer under test is new.

It mirrors `backend.actuation.FaultInjectionHarness` deliberately: the swap
accounting and the "advance the clock, renew, publish, tick" driving are the same
shape the Wave-0A producer-swap proof uses, reused so acceptance ③ exercises that
exact mechanism rather than a parallel one.
"""

from __future__ import annotations

from backend.actuation import (
    ActuationScheduler,
    Emission,
    FakeCanWriter,
    LeaseManager,
    ManualClock,
    TargetMailbox,
    TickTrace,
)
from backend.actuation.can_writer import MIT_BATCH_WIDTH
from backend.actuation.config import LEASE_DURATION_SEC, TICK_INTERVAL_SEC
from backend.jog import JogTrajectory, JogWaypoint, JointJogProducer
from contracts.action import RequestedPositionAction
from contracts.units import Deg, Rad

# A neutral bench pose: unit-tagged zeros standing in for a real joint envelope,
# the same stand-in `FaultInjectionHarness` uses so the bench owns no joint claim.
NEUTRAL_HOLD = tuple(Rad(0.0) for _ in range(MIT_BATCH_WIDTH))
NEUTRAL_REQUEST = RequestedPositionAction(values=tuple(Deg(0.0) for _ in range(MIT_BATCH_WIDTH)))


class JogSchedulerBench:
    """The real scheduler driven by a `JointJogProducer`, on a fake bus and manual clock.

    Ownership: holds the scheduler and its collaborators. `producer` is the currently
    active jog producer; a swap replaces it through the scheduler's atomic transition,
    tracked by `created`/`joined` so a leaked producer is observable.
    """

    def __init__(self, tick_interval_sec: float = TICK_INTERVAL_SEC) -> None:
        """Wire the bench at torque-on with an initial jog producer.

        Args:
            tick_interval_sec: How far the manual clock advances per driven tick.
        """
        self._tick_interval_sec = tick_interval_sec
        self.clock = ManualClock()
        self.can_writer = FakeCanWriter()
        self.mailbox = TargetMailbox()
        self.lease = LeaseManager(LEASE_DURATION_SEC)
        self.trace = TickTrace()
        self._producer_serial = 1
        self.producer = JointJogProducer("jog-1", self.mailbox)
        self.created = 1
        self.joined = 0
        self.scheduler = ActuationScheduler(
            can_writer=self.can_writer,
            mailbox=self.mailbox,
            clock=self.clock,
            lease=self.lease,
            initial_producer=self.producer,
            initial_hold_positions=NEUTRAL_HOLD,
            trace=self.trace,
        )
        # Arm the deadman at torque-on: without a first renewal the opening tick
        # would read an expired lease and hold rather than accept.
        self.lease.renew(self.clock.now())

    def _new_producer(self) -> JointJogProducer:
        """Stand up a fresh jog producer bound to the shared mailbox."""
        self._producer_serial += 1
        return JointJogProducer(f"jog-{self._producer_serial}", self.mailbox)

    def publish_waypoint(self, waypoint: JogWaypoint) -> None:
        """Publish one trajectory waypoint from the active producer at the waypoint's time."""
        self.producer.publish(waypoint.request, waypoint.at)

    def follow_trajectory(self, trajectory: JogTrajectory) -> list[Emission]:
        """Drive the scheduler through a whole trajectory, one waypoint per tick.

        The clock is moved to each waypoint's own time, the lease renewed, the
        waypoint published, then a single tick run — so each interpolated waypoint
        becomes exactly one scheduler emission. The returned emissions are what
        acceptance ② counts.

        Args:
            trajectory: The planned jog trajectory to play out.

        Returns:
            (list[Emission]) One emission per waypoint, in order.
        """
        emissions: list[Emission] = []
        for waypoint in trajectory.waypoints:
            self.clock.advance(waypoint.at - self.clock.now())
            self.lease.renew(self.clock.now())
            self.publish_waypoint(waypoint)
            emissions.append(self.scheduler.tick())
        return emissions

    def run_tick(
        self,
        request: RequestedPositionAction = NEUTRAL_REQUEST,
        publish: bool = True,
        renew: bool = True,
    ) -> Emission:
        """Advance the clock and run one tick, optionally publishing and renewing.

        Args:
            request: The request the active producer publishes when `publish` is set.
            publish: Whether the active producer publishes a fresh target first.
            renew: Whether the deadman lease is renewed first.

        Returns:
            (Emission) The emission the tick produced.
        """
        self.clock.advance(self._tick_interval_sec)
        if renew:
            self.lease.renew(self.clock.now())
        if publish:
            self.producer.publish(request, self.clock.now())
        return self.scheduler.tick()

    def begin_swap(self) -> None:
        """Prepare a new jog producer and open an atomic swap to it."""
        incoming = self._new_producer()
        self.created += 1
        self.scheduler.begin_transition(incoming)
        self.producer = incoming

    def commit_swap(self) -> None:
        """Commit the open swap and join the outgoing producer."""
        outgoing = self.scheduler.commit_transition()
        outgoing.join()
        self.joined += 1
