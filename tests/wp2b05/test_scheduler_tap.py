"""Pattern A end to end — logging rides the one scheduler tick, never the bus (①⑤⑥).

Wires the real Wave-1 scheduler with a `SchedulerLogTap` and drives a hold, an accepted
target, and a stale hold. The tap emits one pos/vel/tau frame per tick from inside the tick,
so the frame count equals the tick count equals the fake writer's send count — logging is
the tick rate, and it cannot outrun it because there is no separate producer of frames.
"""

from __future__ import annotations

from backend.actuation import EmissionLabel
from backend.actuation.mailbox import TimestampedTarget
from backend.friction_log.band import (
    PATTERN_SCHEDULER_TAP,
    achieved_band,
    logging_did_not_outrun_ticks,
)
from contracts.action import RequestedPositionAction
from contracts.units import Deg, Nm
from tests.wp2b05.conftest import Wiring

_WIDTH = 16
_FEEDFORWARD_NM = 3.0


def _publish_target(wiring: Wiring) -> None:
    """Publish a fresh 16-joint target carrying a non-zero feed-forward torque."""
    wiring.mailbox.publish(
        TimestampedTarget(
            request=RequestedPositionAction(values=tuple(Deg(1.0) for _ in range(_WIDTH))),
            published_at=wiring.clock.now(),
            feedforward_torque=tuple(Nm(_FEEDFORWARD_NM) for _ in range(_WIDTH)),
        )
    )


def _tick_an_accepted_target(wiring: Wiring) -> None:
    """Advance, renew the lease, publish, and tick once into an accepted target."""
    wiring.clock.advance(0.001)
    wiring.lease.renew(wiring.clock.now())
    _publish_target(wiring)


def test_tap_emits_one_frame_per_tick_at_the_send_count(wiring: Wiring) -> None:
    """①⑤ Frame count equals tick count equals the CAN send count — logging is the tick."""
    wiring.scheduler.tick()  # mailbox empty -> hold
    _tick_an_accepted_target(wiring)
    accepted = wiring.scheduler.tick()
    wiring.clock.advance(0.1)  # past lease and freshness -> stale hold
    wiring.scheduler.tick()

    assert accepted.label is EmissionLabel.ACCEPTED_TARGET
    assert wiring.sink.count() == wiring.scheduler.tick_index == wiring.writer.write_count == 3
    assert logging_did_not_outrun_ticks(wiring.sink.count(), wiring.scheduler.tick_index)


def test_frame_carries_pos_vel_tau_for_every_joint(wiring: Wiring) -> None:
    """Each frame is a full 16-joint pos/vel/tau record."""
    wiring.scheduler.tick()
    frame = wiring.sink.frames[0]
    assert len(frame.positions) == _WIDTH
    assert len(frame.velocities) == _WIDTH
    assert len(frame.torques) == _WIDTH


def test_accepted_tick_frame_records_the_commanded_torque(wiring: Wiring) -> None:
    """The frame emitted inside the accepted tick carries that tick's feed-forward torque."""
    _tick_an_accepted_target(wiring)
    accepted = wiring.scheduler.tick()

    assert accepted.label is EmissionLabel.ACCEPTED_TARGET
    assert wiring.sink.frames[-1].torques[0] == Nm(_FEEDFORWARD_NM)
    assert wiring.sink.frames[-1].index == wiring.scheduler.tick_index - 1


def test_hold_strips_torque_in_the_logged_frame(wiring: Wiring) -> None:
    """A stale hold logs zero feed-forward torque — a hold is position-only."""
    _tick_an_accepted_target(wiring)
    wiring.scheduler.tick()  # accepted, torque 3.0
    wiring.clock.advance(0.1)  # go stale
    wiring.scheduler.tick()  # hold

    assert wiring.sink.frames[-1].torques[0] == Nm(0.0)


def test_synthetic_band_is_provisional(wiring: Wiring) -> None:
    """A band built here carries no real tick rate or f_max_python, so it is provisional."""
    for _ in range(5):
        wiring.clock.advance(0.001)
        wiring.scheduler.tick()

    band = achieved_band(PATTERN_SCHEDULER_TAP, tuple(wiring.sink.frames))
    assert band.provisional is True
    assert band.tick_rate_hz is None
    assert band.stats.frame_count == wiring.sink.count()
