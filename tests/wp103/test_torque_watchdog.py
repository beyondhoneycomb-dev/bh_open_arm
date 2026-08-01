"""FR-MOT-058 ② — the action-stream watchdog: silence drives the feed-forward torque to zero.

Clamping a torque bounds how hard the arm pushes; it says nothing about how long. A producer
that dies mid-stream leaves its last command standing, and a standing feed-forward torque on a
brakeless arm keeps pushing against whatever it was pushing against. So the interval since the
last judged command is fed to the gateway's FRESHNESS stage, and a gap wider than
`GATEWAY_FRESHNESS_WINDOW_SEC` holds the arm at its present pose with every joint's torque
zeroed.

The distinction this file has to keep visible: **tau to zero is not torque off.** Cutting torque
on this arm is a fall — `04` §2 states it carries no mechanical brake. The watchdog's degradation
is a powered hold: the position command becomes the present pose and the feed-forward term
becomes zero, while the hold gains keep standing.

The judgement is per gap, not a latch: the tick after a hold measures from the held command,
so a stream that resumes is live again on its next command. That matches the scheduler's own
STALE_SOURCE_HOLD (`backend.actuation.decider.decide`), which is re-decided every tick rather
than held until an acknowledgement — the latch is the collision guard's mechanism, not this one.
"""

from __future__ import annotations

from collections.abc import Callable

from backend.actuation import ManualClock, SafetyReason
from backend.actuation.config import FRESHNESS_WINDOW_SEC
from backend.calibration.schema import MOTOR_ORDER
from packages.lerobot_robot_openarm.openarm_follower_oa import (
    CONTROL_PERIOD_SEC,
    GATEWAY_FRESHNESS_WINDOW_SEC,
    NO_FEEDFORWARD_TORQUE_NM,
    OaOpenArmFollower,
)

# The same small move the rest of the torque path uses: 1 deg in one control period clears
# every rate guard from rest.
SMALL_MOVE_DEG = 1.0

# The joint the cases command a torque on, and a value well inside its 40 Nm band.
SHOULDER_MOTOR = MOTOR_ORDER[0]
SHOULDER_INDEX = 0
ROUTED_SHOULDER_TORQUE_NM = 5.0

# A silence no plausible window admits: one second is fifty control periods, so a case built
# on it fails if the window is widened as surely as if the gap stopped being measured. Stated
# absolutely rather than as `window + epsilon`, because a case phrased in terms of the bound it
# is testing moves with the bound and can only ever catch a deleted comparison.
LONG_SILENCE_SEC = 1.0

# The two gaps that bracket the window itself, one millisecond apart and both absolute for the
# reason above: 1.0 s catches a comparison that stopped happening, and only a pair straddling
# the real value catches a window that was widened or narrowed and still compares.
LAST_LIVE_GAP_SEC = 0.050
FIRST_STALE_GAP_SEC = 0.051

# The relation the window and the control period stand in. A stream keeping its declared period
# is never stale, and one that misses this many consecutive periods always is — the two are what
# a window is chosen for, and neither constant states it alone.
MISSED_PERIODS_ALWAYS_STALE = 3

# A clock start far from zero, so a first command judged against a bare `now` rather than
# against "no previous command" would read as ancient instead of accidentally passing.
LATE_CLOCK_START_SEC = 10_000.0


def small_move() -> dict[str, float]:
    """A position action that clears every rate guard on the first command from rest."""
    return {f"{motor}.pos": SMALL_MOVE_DEG for motor in MOTOR_ORDER[:-1]}


def torque_command() -> dict[str, float]:
    """A feed-forward torque on the shoulder, inside its band."""
    return {SHOULDER_MOTOR: ROUTED_SHOULDER_TORQUE_NM}


def test_the_watchdog_window_is_the_spine_freshness_window() -> None:
    """The interval is taken from the actuation spine, not invented for this path.

    Two numbers for "how old is too old" is two answers to one question, and the one this
    path would own is the one nobody would update when the loop rate is finally measured.
    """
    assert GATEWAY_FRESHNESS_WINDOW_SEC == FRESHNESS_WINDOW_SEC


def test_the_window_admits_the_declared_period_and_refuses_three_missed_ones() -> None:
    """The window and the control period stand in a relation, and it is held here.

    Either constant can be moved on its own, and both are owned elsewhere — the window by the
    actuation spine, the period by this path's bootstrap loop rate. What makes the pair usable
    is the relation between them, and a relation asserted in a comment is a relation nobody
    checks: raise the period past the window and every command is born stale, drop the window
    under it and a healthy stream is refused at its own declared rate.
    """
    assert GATEWAY_FRESHNESS_WINDOW_SEC >= CONTROL_PERIOD_SEC
    assert GATEWAY_FRESHNESS_WINDOW_SEC < MISSED_PERIODS_ALWAYS_STALE * CONTROL_PERIOD_SEC


def test_the_first_command_of_a_session_is_not_stale(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """Nothing preceded the opening command, so it is not late — refusing it would deadlock."""
    follower = make_follower(clock=ManualClock(start=LATE_CLOCK_START_SEC))

    follower.send_action(small_move(), feedforward_torque_nm=torque_command())

    result = follower.last_gate_result
    assert result is not None
    assert not result.rejected
    assert result.feedforward_torque_nm[SHOULDER_INDEX].value == ROUTED_SHOULDER_TORQUE_NM


def test_a_stream_keeping_its_period_stays_live(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """A producer running at the declared control period is never stale, and its torque stands."""
    clock = ManualClock()
    follower = make_follower(clock=clock)

    follower.send_action(small_move(), feedforward_torque_nm=torque_command())
    clock.advance(CONTROL_PERIOD_SEC)
    follower.send_action(small_move(), feedforward_torque_nm=torque_command())

    result = follower.last_gate_result
    assert result is not None
    assert not result.rejected
    assert result.feedforward_torque_nm[SHOULDER_INDEX].value == ROUTED_SHOULDER_TORQUE_NM


def test_a_gap_exactly_at_the_window_is_still_live(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """The window is the last admissible age, not the first refused one."""
    clock = ManualClock()
    follower = make_follower(clock=clock)

    follower.send_action(small_move(), feedforward_torque_nm=torque_command())
    clock.advance(GATEWAY_FRESHNESS_WINDOW_SEC)
    follower.send_action(small_move(), feedforward_torque_nm=torque_command())

    result = follower.last_gate_result
    assert result is not None
    assert not result.rejected


def test_a_fifty_millisecond_gap_is_the_last_one_served(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """Where the window sits, stated as a number: 50 ms of silence is still a live stream.

    Its pair below refuses at 51 ms. The two together are what pin the window's value — a case
    that advances the constant it is testing moves wherever the constant moves, so narrowing the
    window to a single control period would leave every such case passing while a stream running
    at its own declared rate is refused.
    """
    clock = ManualClock()
    follower = make_follower(clock=clock)

    follower.send_action(small_move(), feedforward_torque_nm=torque_command())
    clock.advance(LAST_LIVE_GAP_SEC)
    follower.send_action(small_move(), feedforward_torque_nm=torque_command())

    result = follower.last_gate_result
    assert result is not None
    assert not result.rejected
    assert result.feedforward_torque_nm[SHOULDER_INDEX].value == ROUTED_SHOULDER_TORQUE_NM


def test_a_fifty_one_millisecond_gap_is_the_first_one_refused(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """One millisecond past the window the stream is stale and the torque is gone.

    The refusal edge, unlike the admissible one, is where a widened window hides: at twice or
    at nineteen times the real value every other case in this file still passes, because the
    only other refusal here is a full second of silence.
    """
    clock = ManualClock()
    follower = make_follower(clock=clock)

    follower.send_action(small_move(), feedforward_torque_nm=torque_command())
    clock.advance(FIRST_STALE_GAP_SEC)
    follower.send_action(small_move(), feedforward_torque_nm=torque_command())

    result = follower.last_gate_result
    assert result is not None
    assert result.rejected
    assert result.reason is SafetyReason.STALE_SOURCE
    assert all(torque.value == NO_FEEDFORWARD_TORQUE_NM for torque in result.feedforward_torque_nm)


def test_silence_past_the_window_zeroes_the_feedforward_torque(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """The command after a lapse carries no torque, whatever it asked for (`03` FR-MOT-058 ②)."""
    clock = ManualClock()
    follower = make_follower(clock=clock)

    follower.send_action(small_move(), feedforward_torque_nm=torque_command())
    clock.advance(LONG_SILENCE_SEC)
    follower.send_action(small_move(), feedforward_torque_nm=torque_command())

    result = follower.last_gate_result
    assert result is not None
    assert result.rejected
    assert result.reason is SafetyReason.STALE_SOURCE
    assert all(torque.value == NO_FEEDFORWARD_TORQUE_NM for torque in result.feedforward_torque_nm)


def test_the_lapsed_command_holds_the_present_pose_rather_than_dropping_torque(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """The degradation is a powered hold: the requested move is refused, the arm is not dropped.

    On an arm with no mechanical brake these are opposite outcomes, and the returned action
    alone cannot tell them apart — a disable would also stop the move. The bus counter can.
    """
    clock = ManualClock()
    follower = make_follower(clock=clock)
    present = follower.send_action(small_move(), feedforward_torque_nm=torque_command())
    assert present[f"{SHOULDER_MOTOR}.pos"] == SMALL_MOVE_DEG

    clock.advance(LONG_SILENCE_SEC)
    applied = follower.send_action(small_move(), feedforward_torque_nm=torque_command())

    assert applied == {f"{motor}.pos": 0.0 for motor in MOTOR_ORDER}
    assert follower.bus.disable_calls == 0
    assert follower.is_torque_enabled is False


def test_the_stream_is_live_again_on_the_command_after_the_hold(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """The hold is one command's verdict, not a latch — a resumed producer is served again."""
    clock = ManualClock()
    follower = make_follower(clock=clock)

    follower.send_action(small_move(), feedforward_torque_nm=torque_command())
    clock.advance(LONG_SILENCE_SEC)
    follower.send_action(small_move(), feedforward_torque_nm=torque_command())
    clock.advance(CONTROL_PERIOD_SEC)
    follower.send_action(small_move(), feedforward_torque_nm=torque_command())

    result = follower.last_gate_result
    assert result is not None
    assert not result.rejected
    assert result.feedforward_torque_nm[SHOULDER_INDEX].value == ROUTED_SHOULDER_TORQUE_NM
