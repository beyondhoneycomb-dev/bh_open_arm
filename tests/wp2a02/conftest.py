"""WP-2A-02 harness — the deadman driven against the *real* Wave-1 spine.

The point of building on the real scheduler rather than a mock is that the safety
claims are only worth anything if the actual `SAFETY_LATCH_HOLD` the scheduler emits
is what a latched deadman produces. So the harness composes the genuine Wave-1
primitives this WP reuses — `LeaseManager` (the renewal timer), `ActuationScheduler`
(the single CAN writer and its `SafetyLatch`), `FakeCanWriter`, `TargetMailbox`,
`MailboxProducer`, and `ManualClock` — and layers only `DeadmanController` on top.

Determinism: the clock moves only when the harness advances it, so "the tick the
lease expired" is a reproducible fact, not a race. The client clock is modelled as
the server clock plus a fixed skew, so age-filter tests can issue a renewal with a
chosen transit delay without any wall-clock dependence.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.actuation import (
    ActuationScheduler,
    Emission,
    FakeCanWriter,
    LeaseManager,
    MailboxProducer,
    ManualClock,
    TargetMailbox,
    TickTrace,
)
from backend.actuation.can_writer import MIT_BATCH_WIDTH
from backend.deadman import DeadmanController, LeaseRenewal, RenewalResult
from contracts.action import RequestedPositionAction
from contracts.units import Deg, Rad

# A neutral, unit-tagged request and hold pose. Zero is not a claim about the arm;
# it is a well-formed stand-in so the harness has a target to publish and a pose to
# hold at without owning any real joint envelope.
NEUTRAL_REQUEST = RequestedPositionAction(values=tuple(Deg(0.0) for _ in range(MIT_BATCH_WIDTH)))
NEUTRAL_HOLD = tuple(Rad(0.0) for _ in range(MIT_BATCH_WIDTH))

# Bench timings. The tick interval is far below the lease duration so an expiry
# lands on a well-separated tick; the values are harness knobs, not loop-rate claims.
TICK_INTERVAL_SEC = 0.001
LEASE_DURATION_SEC = 0.1
MAX_LEASE_AGE_SEC = 0.05


@dataclass
class RenewalStreamState:
    """Per-generation renewal bookkeeping the harness keeps for the client side.

    Attributes:
        sequence: The last sequence the harness emitted for the active generation.
    """

    sequence: int = 0


class DeadmanHarness:
    """The deadman on the real spine, with levers for every acceptance scenario."""

    def __init__(
        self,
        lease_duration_sec: float = LEASE_DURATION_SEC,
        max_lease_age_sec: float = MAX_LEASE_AGE_SEC,
        tick_interval_sec: float = TICK_INTERVAL_SEC,
        client_skew_sec: float = 0.0,
    ) -> None:
        """Assemble the spine and the deadman on top of it.

        Args:
            lease_duration_sec: Deadman lease duration, shared by the `LeaseManager`
                and the controller so expiry has one definition.
            max_lease_age_sec: Age past which a renewal is discarded.
            tick_interval_sec: How far the clock advances per tick.
            client_skew_sec: A fixed offset added to the server clock to model the
                client's monotonic clock, so age tests can inject transit delay.
        """
        self.clock = ManualClock()
        self.lease = LeaseManager(lease_duration_sec)
        self.can_writer = FakeCanWriter()
        self.mailbox = TargetMailbox()
        self.trace = TickTrace()
        self.producer = MailboxProducer("deadman-harness", self.mailbox, self.clock)
        self.scheduler = ActuationScheduler(
            can_writer=self.can_writer,
            mailbox=self.mailbox,
            clock=self.clock,
            lease=self.lease,
            initial_producer=self.producer,
            initial_hold_positions=NEUTRAL_HOLD,
            trace=self.trace,
        )
        self.controller = DeadmanController(
            self.lease,
            self.scheduler,
            self.clock,
            lease_duration_sec=lease_duration_sec,
            max_lease_age_sec=max_lease_age_sec,
        )
        self._tick_interval_sec = tick_interval_sec
        self._client_skew_sec = client_skew_sec
        self._stream = RenewalStreamState()

    def advance(self) -> None:
        """Move the clock forward by one tick interval."""
        self.clock.advance(self._tick_interval_sec)

    def publish(self) -> None:
        """Publish a fresh neutral target from the active producer."""
        self.producer.publish(NEUTRAL_REQUEST)

    def build_renewal(
        self,
        sequence: int | None = None,
        generation: int | None = None,
        issued_mono_client: float | None = None,
    ) -> LeaseRenewal:
        """Construct a renewal for the current tick, defaulting each field sanely.

        Args:
            sequence: Explicit sequence, or the next auto-incremented one.
            generation: Explicit generation, or the controller's current one.
            issued_mono_client: Explicit client issue time, or the current client
                clock (server clock plus the configured skew).

        Returns:
            (LeaseRenewal) The renewal to feed to the controller.
        """
        if sequence is None:
            self._stream.sequence += 1
            sequence = self._stream.sequence
        return LeaseRenewal(
            generation=self.controller.current_generation if generation is None else generation,
            sequence=sequence,
            issued_mono_client=(
                self.clock.now() + self._client_skew_sec
                if issued_mono_client is None
                else issued_mono_client
            ),
        )

    def renew(
        self,
        sequence: int | None = None,
        generation: int | None = None,
        issued_mono_client: float | None = None,
    ) -> RenewalResult:
        """Send one renewal through the controller at the current clock time.

        Returns:
            (RenewalResult) The controller's verdict.
        """
        return self.controller.receive_renewal(
            self.build_renewal(sequence, generation, issued_mono_client)
        )

    def reset_stream(self) -> None:
        """Reset the client sequence counter, for a fresh generation after re-arm."""
        self._stream.sequence = 0

    def tick(self, publish: bool = True, renew: bool = True) -> Emission:
        """Advance one tick: optionally renew and publish, then poll, then run the tick.

        The poll runs before the scheduler tick so an expiry this tick latches before
        the frame is written and the same tick emits the latch hold.

        Args:
            publish: Whether the producer publishes a fresh target first.
            renew: Whether a renewal is sent first.

        Returns:
            (Emission) The emission the scheduler produced.
        """
        self.advance()
        if renew:
            self.renew()
        if publish:
            self.publish()
        self.controller.poll()
        return self.scheduler.tick()

    def take_deadman(self) -> RenewalResult:
        """Advance one tick and send the first renewal, arming the live lease.

        Returns:
            (RenewalResult) The first renewal's verdict (accepted).
        """
        self.advance()
        result = self.renew()
        self.publish()
        self.controller.poll()
        self.scheduler.tick()
        return result

    def run_until_latched(self, max_ticks: int) -> int:
        """Stop renewing and tick until the deadman latches; return the tick offset.

        Args:
            max_ticks: Ceiling on ticks to run before giving up.

        Returns:
            (int) The 0-based tick offset at which the latch engaged.

        Raises:
            AssertionError: If the latch did not engage within `max_ticks`.
        """
        for offset in range(max_ticks):
            self.tick(publish=True, renew=False)
            if self.controller.latched:
                return offset
        raise AssertionError(f"deadman did not latch within {max_ticks} ticks")
