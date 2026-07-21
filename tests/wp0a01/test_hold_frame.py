"""Interface contract ⑤/⑥ — one MIT position-hold frame per tick, always audited.

Every tick — accepted or any of the three holds — performs exactly one
`mit_control_batch` write of a full 16-wide MIT frame, and the frame is recorded to
the trace (the `executedMitCommand` audit channel). A hold frame is position-only:
zero feed-forward velocity, zero feed-forward torque, and it holds the last
accepted position. There is no torque-cut path — the CAN writer has no
`disable_torque` method to call.
"""

from __future__ import annotations

from backend.actuation import (
    MIT_BATCH_WIDTH,
    EmissionLabel,
    FakeCanWriter,
    FaultInjectionHarness,
    TickTrace,
)
from contracts.action import RequestedPositionAction
from contracts.units import Deg, Nm, RadPerSec, deg_to_rad


def test_every_tick_writes_exactly_one_full_frame() -> None:
    """One write per tick, each a full 16-wide MIT batch, for every emission type."""
    harness = FaultInjectionHarness(trace=TickTrace(), lease_duration_sec=0.005)
    for _ in range(10):
        harness.run_tick(publish=True, renew=True)
    for _ in range(10):
        harness.run_tick(publish=False, renew=False)

    assert harness.can_writer.write_count == harness.scheduler.tick_index
    last = harness.can_writer.last_batch
    assert last is not None
    assert len(last) == MIT_BATCH_WIDTH


def test_hold_frame_is_position_only_zero_feedforward() -> None:
    """A hold frame carries zero feed-forward velocity and torque (position-only)."""
    harness = FaultInjectionHarness(trace=TickTrace())
    hold = harness.run_tick(publish=False)  # empty mailbox -> hold
    assert hold.label is EmissionLabel.STALE_SOURCE_HOLD
    for command in hold.batch:
        assert command.dq == RadPerSec(0.0)
        assert command.tau == Nm(0.0)


def test_hold_parks_at_last_accepted_position() -> None:
    """After an accepted target, a hold re-sends that position in radians."""
    harness = FaultInjectionHarness(trace=TickTrace(), freshness_window_sec=0.0005)
    request = RequestedPositionAction(values=tuple(Deg(10.0) for _ in range(MIT_BATCH_WIDTH)))
    accepted = harness.run_tick(publish=True, request=request)
    assert accepted.label is EmissionLabel.ACCEPTED_TARGET

    hold = harness.run_tick(publish=False)
    assert hold.label is EmissionLabel.STALE_SOURCE_HOLD
    expected_q = deg_to_rad(Deg(10.0))
    assert all(command.q == expected_q for command in hold.batch)


def test_can_writer_has_no_disable_torque_method() -> None:
    """The stop path cannot cut torque: the CAN writer exposes no such method."""
    assert not hasattr(FakeCanWriter, "disable_torque")
