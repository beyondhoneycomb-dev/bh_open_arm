"""The thread that drives the arm session's tick, and what it does when a tick dies.

A session with no runner is the defect the session was built to remove, one level up: the board
stays empty, the deadman is never polled, and a lapsed lease latches nothing. So the runner is
not an optimisation over calling `tick` in a loop — it is the caller.

What is asserted here is the loop's own behaviour, not its rate. `TickPacer` holds the period in
a kernel timer and `tests/wp103/test_pacer.py` is where that number is measured; a second test
racing the same clock would report the machine's mood.
"""

from __future__ import annotations

import time

import pytest

from backend.actuation.clock import WallClock
from backend.actuation.guard import GuardSample
from backend.actuation.session import ArmFrame, ArmSession
from backend.actuation.session_runner import ArmSessionRunner
from contracts.prim.schema import ARM_SIDES
from contracts.units import Celsius, Deg, DegPerSec, Nm

LEFT = ARM_SIDES[0]
JOINT_COUNT = 8

# Fast enough that a test waiting on a handful of ticks finishes promptly, slow enough that the
# timer is doing the pacing rather than the scheduler. Nothing here asserts the period.
TEST_TICK_HZ = 200.0

# How many ticks a test waits for before judging the loop alive. Above one, so a runner that
# ticked once and fell out of its loop is not mistaken for one that is running.
TICKS_BEFORE_JUDGING = 3

# Ceiling on that wait. It is a liveness bound, not synchronisation: the passing path returns as
# soon as the count is reached.
TICK_WAIT_TIMEOUT_SEC = 5.0

# How many periods of quiet a stopped runner must hold for. Several, so a loop that was between
# two waits when the flag was set has had every chance to tick again.
QUIET_PERIODS_AFTER_STOP = 5

# How long a waiting test sleeps between looks. Shorter than a period so no tick is missed, and
# non-zero so the wait yields the GIL to the thread it is waiting on.
POLL_INTERVAL_SEC = 1.0 / TEST_TICK_HZ / 2


class CountingArm:
    """A read that answers a resting frame and counts the polls, or raises what was armed."""

    def __init__(self) -> None:
        """Start healthy with nothing read."""
        self.reads = 0
        self.failure: Exception | None = None

    def read(self) -> tuple[tuple[Deg, ...], tuple[Nm, ...], GuardSample]:
        """Answer one resting frame, or raise."""
        self.reads += 1
        if self.failure is not None:
            raise self.failure
        return ArmFrame(
            joint_deg=tuple(Deg(0.0) for _ in range(JOINT_COUNT)),
            torque_nm=tuple(Nm(0.0) for _ in range(JOINT_COUNT)),
            velocity_deg_s=tuple(DegPerSec(0.0) for _ in range(JOINT_COUNT)),
            temp_mos_c=tuple(Celsius(0.0) for _ in range(JOINT_COUNT)),
            temp_rotor_c=tuple(Celsius(0.0) for _ in range(JOINT_COUNT)),
            guard=GuardSample.healthy(),
        )


@pytest.fixture
def arm() -> CountingArm:
    """The read the runner drives."""
    return CountingArm()


@pytest.fixture
def session(arm: CountingArm) -> ArmSession:
    """A session on the wall clock, because the runner's pacing is a real timer."""
    return ArmSession(clock=WallClock(), read_arms={LEFT: arm.read})


def _wait_for_ticks(arm: CountingArm, count: int) -> None:
    """Block until the read has been polled `count` times, or fail the test.

    Sleeps a fraction of a period between looks rather than spinning. A spin here holds the GIL
    against the very thread it is waiting for, which turns a healthy runner into a timeout on a
    loaded machine — and the parallel lane runs twenty-four of these at once.
    """
    deadline = WallClock().now() + TICK_WAIT_TIMEOUT_SEC
    while arm.reads < count:
        if WallClock().now() > deadline:
            pytest.fail(f"the runner polled {arm.reads} times in {TICK_WAIT_TIMEOUT_SEC}s")
        time.sleep(POLL_INTERVAL_SEC)


def test_the_runner_keeps_ticking_the_session(session: ArmSession, arm: CountingArm) -> None:
    """The board has a writer only while something is calling `tick`."""
    runner = ArmSessionRunner(session, TEST_TICK_HZ)
    runner.start()
    try:
        _wait_for_ticks(arm, TICKS_BEFORE_JUDGING)
    finally:
        runner.stop()

    assert session.board(LEFT).view().state is not None


def test_stopping_the_runner_stops_the_ticks(session: ArmSession, arm: CountingArm) -> None:
    """A stop that returned while the loop still ran would leave two writers on one board.

    The count is compared across a wait rather than read once: a stop that only set a flag would
    return True on the join timing out nowhere, and the reads would keep climbing behind it.
    """
    runner = ArmSessionRunner(session, TEST_TICK_HZ)
    runner.start()
    _wait_for_ticks(arm, TICKS_BEFORE_JUDGING)

    assert runner.stop() is True
    settled = arm.reads
    time.sleep(QUIET_PERIODS_AFTER_STOP / TEST_TICK_HZ)

    assert arm.reads == settled


def test_a_tick_that_raises_stops_the_loop_and_is_kept(
    session: ArmSession, arm: CountingArm
) -> None:
    """A loop that died silently is a board that stopped advancing and says it is fine.

    `ArmStateView` ages the last frame, so a dead runner does eventually show as staleness — but
    only to a reader that is checking, and only after the deadline. The failure itself is the
    thing worth keeping, because it names why.
    """
    arm.failure = RuntimeError("the bus answered no state")
    runner = ArmSessionRunner(session, TEST_TICK_HZ)
    runner.start()
    # Joined rather than stopped. A failing tick ends the loop by itself, so the thread's own exit
    # is the event to wait for; asking it to stop instead races the first tick — under load the
    # flag can be set before the thread reaches `tick`, and the loop then leaves having recorded
    # nothing, which is correct behaviour and a test that proves nothing.
    runner.join(timeout=TICK_WAIT_TIMEOUT_SEC)

    assert not runner.is_alive()
    assert isinstance(runner.failure, RuntimeError)
    assert runner.ticks == 0


def test_stopping_a_runner_that_never_started_is_not_an_error(session: ArmSession) -> None:
    """Shutdown runs on paths where startup did not finish, and must not raise there."""
    assert ArmSessionRunner(session, TEST_TICK_HZ).stop() is True


def test_a_rate_at_or_below_zero_is_refused(session: ArmSession) -> None:
    """A zero rate arms a one-shot timer, so the loop would block forever on its second wait."""
    with pytest.raises(ValueError, match="above zero"):
        ArmSessionRunner(session, 0.0)
