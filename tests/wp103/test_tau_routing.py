"""Acceptance ⑱ — the feed-forward torque reaches `_mit_control_batch`, tau=0 hardcode released.

LeRobot's stock `send_action` hardcodes `tau` (and `dq`) to 0 (`12` §2.7.0); the
bus-level `_mit_control_batch` already accepts a torque argument (`16` §10.1). So
releasing the hardcode is routing the emitted command's tau into that argument. This
proves the whole path: `positions_to_batch` carries a feed-forward torque, the
scheduler emits it, the `BusCanWriter` forwards it to the bus, and a hold strips it
back to zero because a hold is position-only.
"""

from __future__ import annotations

from backend.actuation import (
    ActuationScheduler,
    BusCanWriter,
    EmissionLabel,
    LeaseManager,
    MailboxProducer,
    ManualClock,
    TargetMailbox,
    TickTrace,
    positions_to_batch,
)
from backend.actuation.mailbox import TimestampedTarget
from contracts.action import ExecutedMitCommand, RequestedPositionAction
from contracts.units import Deg, Nm, Rad, RadPerSec


class _RecordingMitBus:
    """A fake MIT bus that records the last batched command dict it was sent."""

    def __init__(self) -> None:
        self.sent: dict[str, tuple[float, float, float, float, float]] | None = None

    def _mit_control_batch(
        self, commands: dict[str, tuple[float, float, float, float, float]]
    ) -> None:
        self.sent = commands


def test_bus_writer_routes_feedforward_torque_to_the_batch() -> None:
    """The emitted command's tau lands in the fifth `_mit_control_batch` slot (⑱)."""
    bus = _RecordingMitBus()
    writer = BusCanWriter(bus, ("joint_1", "joint_2"))
    batch = (
        ExecutedMitCommand(kp=40.0, kd=1.0, q=Rad(0.1), dq=RadPerSec(0.0), tau=Nm(7.5)),
        ExecutedMitCommand(kp=40.0, kd=1.0, q=Rad(0.2), dq=RadPerSec(0.0), tau=Nm(0.0)),
    )
    writer.mit_control_batch(batch)

    assert bus.sent is not None
    # The torque is not hardcoded to zero: joint_1's fifth tuple element is the routed tau.
    assert bus.sent["joint_1"][4] == 7.5
    assert bus.sent["joint_2"][4] == 0.0
    assert writer.write_count == 1


def test_position_only_command_carries_zero_torque() -> None:
    """Without a feed-forward torque, the batch is position-only (tau=0), the default."""
    batch = positions_to_batch((Rad(0.1), Rad(0.2)))
    assert all(command.tau.value == 0.0 for command in batch)


def test_feedforward_torque_flows_through_scheduler_and_hold_strips_it() -> None:
    """The scheduler emits the routed tau, and the next hold strips it back to zero (⑱)."""
    width = 16
    clock = ManualClock()
    mailbox = TargetMailbox()
    lease = LeaseManager(0.1)
    producer = MailboxProducer("p", mailbox, clock)
    bus = _RecordingMitBus()
    writer = BusCanWriter(bus, tuple(f"m{index}" for index in range(width)))
    scheduler = ActuationScheduler(
        writer,
        mailbox,
        clock,
        lease,
        producer,
        tuple(Rad(0.0) for _ in range(width)),
        TickTrace(),
    )
    lease.renew(clock.now())

    clock.advance(0.001)
    lease.renew(clock.now())
    mailbox.publish(
        TimestampedTarget(
            request=RequestedPositionAction(values=tuple(Deg(1.0) for _ in range(width))),
            published_at=clock.now(),
            feedforward_torque=tuple(Nm(3.0) for _ in range(width)),
        )
    )
    accepted = scheduler.tick()
    assert accepted.label is EmissionLabel.ACCEPTED_TARGET
    assert accepted.batch[0].tau.value == 3.0
    assert bus.sent is not None
    assert bus.sent["m0"][4] == 3.0

    # Let the source go stale; the next tick holds and the hold is position-only.
    clock.advance(0.1)
    held = scheduler.tick()
    assert held.is_hold
    assert held.batch[0].tau.value == 0.0
    assert bus.sent["m0"][4] == 0.0
