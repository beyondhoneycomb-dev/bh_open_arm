"""CG-4A-07e — 100 backend switches leave residuals at 0 and the connection untouched.

SPINE §2-2 / `FR-INF-021`: switching backend resets policy state, the action queue, and
the interpolator, but keeps the robot connected — because `connect()` unconditionally
re-zeros the arm (`FR-OPS-065/083`), so a reconnect on every switch would destroy the
zero point. The test dirties the RTC buffers before each switch so the reset-to-0 is a
real observation, cycles all three backends 100 times, and asserts the `connect()` call
count never moves off the caller's single connect.
"""

from __future__ import annotations

from backend.actuation import ManualClock, TargetMailbox
from backend.inference.adapter import (
    ActParams,
    BackendParams,
    InferenceBackend,
    InferenceSession,
    RemoteParams,
    RtcParams,
)
from tests.wp4a07.support import FixturePolicy, make_counting_robot

_SEQUENCE: list[tuple[InferenceBackend, BackendParams]] = [
    (InferenceBackend.SYNC, ActParams()),
    (InferenceBackend.RTC, RtcParams()),
    (InferenceBackend.REMOTE_GRPC, RemoteParams(actions_per_chunk=8)),
]

# RTC ticks run to dirty the buffers before a switch. Six lands mid-interpolation with a
# non-empty queue (interpolation_steps=4), so both residuals are > 0 to be reset.
_DIRTY_TICKS = 6
_SWITCHES = 100


def test_hundred_switches_reset_buffers_and_keep_connection() -> None:
    """100 switches: residual 0 after each, policy reset each time, connect count unchanged."""
    robot = make_counting_robot()
    assert robot.connect_calls == 1

    policy = FixturePolicy(relative_action=False)
    session = InferenceSession(
        robot=robot,
        mailbox=TargetMailbox(),
        clock=ManualClock(),
        policy=policy,
        fps=30.0,
        interpolation_steps=4,
    )
    session.switch_backend(*_SEQUENCE[0])

    interpolator_dirtied = False
    for index in range(_SWITCHES):
        if session.backend is InferenceBackend.RTC:
            for _ in range(_DIRTY_TICKS):
                session.rtc_tick()
            assert session.queue_residual > 0
            interpolator_dirtied = interpolator_dirtied or session.interpolator_residual > 0

        resets_before = policy.reset_calls
        session.switch_backend(*_SEQUENCE[(index + 1) % len(_SEQUENCE)])

        assert session.queue_residual == 0
        assert session.interpolator_residual == 0
        assert policy.reset_calls == resets_before + 1

    assert robot.connect_calls == 1
    assert robot.disconnect_calls == 0
    assert interpolator_dirtied


def test_switch_resets_a_dirtied_queue_without_reconnecting() -> None:
    """A focused view: fill the RTC queue, switch, and see it emptied with no reconnect."""
    robot = make_counting_robot()
    session = InferenceSession(
        robot=robot,
        mailbox=TargetMailbox(),
        clock=ManualClock(),
        policy=FixturePolicy(),
        fps=30.0,
        interpolation_steps=4,
    )
    session.switch_backend(InferenceBackend.RTC, RtcParams())
    for _ in range(_DIRTY_TICKS):
        session.rtc_tick()
    assert session.queue_residual > 0
    assert session.interpolator_residual > 0

    session.switch_backend(InferenceBackend.SYNC, ActParams())
    assert session.queue_residual == 0
    assert session.interpolator_residual == 0
    assert robot.connect_calls == 1
