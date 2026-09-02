"""The state board: one writer, lock-free readers, and a staleness rule that needs two facts.

The rule is where the tests earn their place. "A reading older than N seconds means stop" is the
obvious one and it is wrong — a connected GUI between operator actions reads nothing and drives
nothing, and that rule stops the arm for standing still. The condition is narrower: a command
that outlived the reading it was built on. Both directions are pinned here, because the negative
is the one that cost the sibling rig four failing tests to find.
"""

from __future__ import annotations

from backend.actuation.board import ArmState, ArmStateBoard, ArmStateView
from backend.actuation.clock import ManualClock
from backend.actuation.guard import GuardSample
from contracts.units import Celsius, Deg, DegPerSec, Nm

# The deadline a driven arm's reading may not exceed. Any value works; it is a parameter of the
# rule, not of the board.
MAX_AGE_S = 0.5

# A reading's worth of joints. Two rather than the full width: this file is about the board, and a
# 16-wide fixture would only make the assertions longer.
JOINTS = (Deg(10.0), Deg(-20.0))
TORQUES = (Nm(0.5), Nm(-0.25))
VELOCITIES = (DegPerSec(1.5), DegPerSec(-0.75))
TEMPS_MOS = (Celsius(41.0), Celsius(39.5))
TEMPS_ROTOR = (Celsius(37.0), Celsius(36.5))


def _state(read_at: float, tick_index: int = 0) -> ArmState:
    """One reading, taken at `read_at`."""
    return ArmState(
        read_at=read_at,
        joint_deg=JOINTS,
        torque_nm=TORQUES,
        velocity_deg_s=VELOCITIES,
        temp_mos_c=TEMPS_MOS,
        temp_rotor_c=TEMPS_ROTOR,
        guard=GuardSample.healthy(),
        tick_index=tick_index,
    )


def test_a_board_that_has_published_nothing_says_so() -> None:
    """No reading is not a zero reading. A caller must be able to tell them apart."""
    view = ArmStateBoard(clock=ManualClock()).view()

    assert view.state is None
    assert view.age_s == float("inf")
    assert not view.commanded_since_read


def test_a_published_reading_comes_back_whole() -> None:
    """Pose and torque travel together because they came from one frame."""
    clock = ManualClock()
    board = ArmStateBoard(clock=clock)
    board.publish(_state(read_at=clock.now(), tick_index=7))

    view = board.view()

    assert view.state is not None
    assert view.state.joint_deg == JOINTS
    assert view.state.torque_nm == TORQUES
    assert view.state.tick_index == 7


def test_the_age_is_measured_from_the_reading_not_from_the_publish() -> None:
    """A reading carries when it was taken, so a slow publish does not make it look fresh."""
    clock = ManualClock()
    board = ArmStateBoard(clock=clock)
    taken_at = clock.now()
    clock.advance(0.1)
    board.publish(_state(read_at=taken_at))

    assert board.view().age_s == 0.1


def test_publishing_again_replaces_the_reading() -> None:
    """One slot, latest wins. A reader never sees a queue of readings it has to drain."""
    clock = ManualClock()
    board = ArmStateBoard(clock=clock)
    board.publish(_state(read_at=clock.now(), tick_index=1))
    clock.advance(0.01)
    board.publish(_state(read_at=clock.now(), tick_index=2))

    view = board.view()

    assert view.state is not None
    assert view.state.tick_index == 2
    assert view.age_s == 0.0


def test_an_idle_arm_is_never_stale() -> None:
    """The negative that the age-alone rule gets wrong.

    Nobody has read for a long time and nobody has commanded. That is a connected GUI between
    operator actions, and stopping the arm for it is stopping it for standing still.
    """
    clock = ManualClock()
    board = ArmStateBoard(clock=clock)
    board.publish(_state(read_at=clock.now()))
    clock.advance(MAX_AGE_S * 10.0)

    assert not board.view().is_driving_blind(MAX_AGE_S)


def test_a_command_before_the_reading_does_not_arm_the_deadline() -> None:
    """A healthy loop reads then sends, so its last command is newer than its last read.

    The arming condition is a command that OUTLIVED its reading, not merely a command — a rule
    keyed on "has ever commanded" would latch every healthy loop the moment it went quiet.
    """
    clock = ManualClock()
    board = ArmStateBoard(clock=clock)
    board.mark_commanded(clock.now())
    clock.advance(0.01)
    board.publish(_state(read_at=clock.now()))
    clock.advance(MAX_AGE_S * 10.0)

    assert not board.view().is_driving_blind(MAX_AGE_S)


def test_commanding_past_a_stale_reading_is_driving_blind() -> None:
    """The failure the deadline exists for: frames going out with no idea where the joint is."""
    clock = ManualClock()
    board = ArmStateBoard(clock=clock)
    board.publish(_state(read_at=clock.now()))
    clock.advance(MAX_AGE_S * 2.0)
    board.mark_commanded(clock.now())

    assert board.view().is_driving_blind(MAX_AGE_S)


def test_a_fresh_reading_under_command_is_not_blind() -> None:
    """The rule is not vacuous: a loop that reads and sends every tick must pass it."""
    clock = ManualClock()
    board = ArmStateBoard(clock=clock)
    board.publish(_state(read_at=clock.now()))
    clock.advance(MAX_AGE_S / 10.0)
    board.mark_commanded(clock.now())

    assert not board.view().is_driving_blind(MAX_AGE_S)


def test_a_reading_that_arrives_after_the_command_clears_the_arming() -> None:
    """A loop that resumes reading stops being blind, without anyone acknowledging anything.

    Staleness is a fact about the last two events, not a latch. The latch is `SafetyLatch`'s job
    and it is one-way on purpose; this must not become a second one that nothing can clear.
    """
    clock = ManualClock()
    board = ArmStateBoard(clock=clock)
    board.publish(_state(read_at=clock.now()))
    clock.advance(MAX_AGE_S * 2.0)
    board.mark_commanded(clock.now())
    assert board.view().is_driving_blind(MAX_AGE_S)

    board.publish(_state(read_at=clock.now()))

    assert not board.view().is_driving_blind(MAX_AGE_S)


def test_two_boards_do_not_see_each_others_arm() -> None:
    """The board is owned by whoever owns the arm; a process-wide one would cross two rigs."""
    clock = ManualClock()
    left = ArmStateBoard(clock=clock)
    right = ArmStateBoard(clock=clock)
    left.publish(_state(read_at=clock.now(), tick_index=1))

    assert right.view().state is None
    assert left.view().state is not None


def test_a_view_is_frozen_so_a_reader_cannot_edit_the_arm() -> None:
    """A reader holds a value, not a handle. Nothing downstream can write back through it."""
    clock = ManualClock()
    board = ArmStateBoard(clock=clock)
    board.publish(_state(read_at=clock.now()))
    view = board.view()

    assert isinstance(view, ArmStateView)
    assert type(view).__dataclass_params__.frozen
    assert type(view.state).__dataclass_params__.frozen


def test_the_never_commanded_sentinel_is_below_every_instant_a_clock_can_report() -> None:
    """A clock is not required to start at or above zero, and the sentinel has to survive that.

    `ManualClock` takes a start, and a negative one is what a test placing an expiry before its
    origin uses. With a sentinel of 0.0 such a clock reports the FIRST reading as already
    commanded — `0.0 > -5.0` — and arms the blind-driving deadline on an arm nothing has ever
    sent a frame to.

    `WallClock` does not distinguish the two: `time.monotonic()` is always above zero, so 0.0 sits
    below every reading it produces. That is why the sentinel is negative infinity rather than
    zero, and why this test uses the clock that can actually tell them apart.
    """
    clock = ManualClock(start=-5.0)
    board = ArmStateBoard(clock=clock)
    board.publish(_state(read_at=clock.now()))

    view = board.view()

    assert not view.commanded_since_read
    assert not view.is_driving_blind(MAX_AGE_S)
