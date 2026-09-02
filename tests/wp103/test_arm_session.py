"""The arm session — one process, one latch, one board per side, one tick.

Every defect this exists to remove is a missing caller rather than missing code. `ArmStateBoard`
has had no production writer since it landed; `DeadmanController.poll` names its call contract —
once per tick — and nothing ticked; the `SafetyLatch` a GUI stop engages had no owner in the
process that serves the GUI. One object holding all three is what turns those into one wiring.

The two counts are the thing to keep straight, and each has a test here: one latch, because a
stop is a fact about the rig and a second latch would stop half a machine; one board per side,
because a reading is a fact about one arm and `ArmState` carries no side dimension.
"""

from __future__ import annotations

import pytest

from backend.actuation.clock import ManualClock
from backend.actuation.guard import GuardSample
from backend.actuation.session import ArmFrame, ArmSession
from backend.deadman import DEADMAN_LEASE_DURATION_SEC, LeaseRenewal
from contracts.prim.schema import ARM_SIDES
from contracts.units import Celsius, Deg, DegPerSec, Nm
from ops.cancel.scheduler import LatchReason

LEFT, RIGHT = ARM_SIDES

# One frame's worth of arm, distinct per joint so a vector assembled in the wrong order fails.
POSE_DEG = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 0.0)
TORQUE_NM = (0.5, -1.5, 2.5, -3.5, 4.5, -5.5, 6.5, 0.0)
# Distinct per joint and distinct from the pose and the torque: a channel assembled from the
# wrong source passes against a constant vector and fails against these.
VELOCITY_DEG_S = (0.1, -0.2, 0.3, -0.4, 0.5, -0.6, 0.7, 0.0)
TEMP_MOS_C = (40.0, 41.0, 42.0, 43.0, 44.0, 45.0, 46.0, 0.0)
TEMP_ROTOR_C = (30.0, 31.0, 32.0, 33.0, 34.0, 35.0, 36.0, 0.0)

# What one read costs on the clock. Non-zero so `read_at` cannot be confused with the instant
# the tick started, which is what a board age is measured against.
READ_DURATION_SEC = 0.002


class RecordingArm:
    """A read that answers a fixed frame and counts how many times it was asked.

    Reading advances the clock, because that is what a bus read does: the tick's cost is the
    round trip, and a double that made reading free would let a test assert an age no real loop
    can produce.
    """

    def __init__(self, clock: ManualClock) -> None:
        """Bind the double to the clock its reads consume time on."""
        self._clock = clock
        self.reads = 0
        self.failure: Exception | None = None

    def read(self) -> ArmFrame:
        """Answer one frame, or raise what the test armed."""
        self.reads += 1
        self._clock.advance(READ_DURATION_SEC)
        if self.failure is not None:
            raise self.failure
        return ArmFrame(
            joint_deg=tuple(Deg(value) for value in POSE_DEG),
            torque_nm=tuple(Nm(value) for value in TORQUE_NM),
            velocity_deg_s=tuple(DegPerSec(value) for value in VELOCITY_DEG_S),
            temp_mos_c=tuple(Celsius(value) for value in TEMP_MOS_C),
            temp_rotor_c=tuple(Celsius(value) for value in TEMP_ROTOR_C),
            guard=GuardSample.healthy(),
        )


@pytest.fixture
def clock() -> ManualClock:
    """The one monotonic source the session, the board and the deadman share."""
    return ManualClock()


@pytest.fixture
def arm(clock: ManualClock) -> RecordingArm:
    """The read the session drives once per tick."""
    return RecordingArm(clock)


@pytest.fixture
def session(clock: ManualClock, arm: RecordingArm) -> ArmSession:
    """A session over the manual clock and the recording read."""
    return ArmSession(clock=clock, read_arms={LEFT: arm.read})


def test_a_tick_publishes_the_frame_the_read_answered(session: ArmSession) -> None:
    """The board's first production writer puts one read on the board, whole."""
    session.tick()

    state = session.board(LEFT).view().state
    assert state is not None
    assert tuple(value.value for value in state.joint_deg) == POSE_DEG
    assert tuple(value.value for value in state.torque_nm) == TORQUE_NM


def test_one_tick_reads_the_arm_exactly_once(session: ArmSession, arm: RecordingArm) -> None:
    """The pose and the torque on the board describe one instant, which needs one read.

    A second read per tick is the arrangement the board exists to remove: it puts a pose beside
    a torque from a different frame, and doubles the traffic on the loop that keeps a brakeless
    arm up.
    """
    session.tick()

    assert arm.reads == 1


def test_the_reading_is_stamped_when_the_read_finished(
    session: ArmSession, clock: ManualClock
) -> None:
    """`read_at` is the instant the answer arrived, not the instant the tick began.

    An age measured from the start of the tick under-reports by the whole round trip, and the
    round trip is the part that grows when the bus is in trouble — so the number would be
    smallest exactly when the staleness it feeds matters most.
    """
    session.tick()

    state = session.board(LEFT).view().state
    assert state is not None
    assert state.read_at == clock.now()


def test_ticks_are_numbered_so_two_identical_readings_differ(session: ArmSession) -> None:
    """An arm holding still publishes the same values forever; the index is what advances."""
    session.tick()
    first = session.board(LEFT).view().state
    session.tick()
    second = session.board(LEFT).view().state

    assert first is not None
    assert second is not None
    assert second.tick_index == first.tick_index + 1


def test_a_read_that_raises_leaves_the_last_good_frame_standing(
    session: ArmSession, arm: RecordingArm
) -> None:
    """A failed read publishes nothing rather than a frame with a hole in it.

    Widening a partial read into a full one is how a fabricated zero reaches a reader as a
    measurement — the same substitution `_poll_states` refuses at the bus. The previous frame
    stays, and it ages, which is the signal a reader already knows how to act on.
    """
    session.tick()
    good = session.board(LEFT).view().state
    arm.failure = RuntimeError("the bus answered no state")

    with pytest.raises(RuntimeError):
        session.tick()

    assert session.board(LEFT).view().state is good


def test_a_stop_engages_the_same_latch_the_deadman_reads(session: ArmSession) -> None:
    """One latch, not two. Two would mean a stop the deadman cannot see."""
    session.engage_safety_latch(_stop_reason(at=0.0))

    assert session.latch_active
    assert session.deadman.latched


def test_only_the_rearm_handshake_clears_the_latch(session: ArmSession) -> None:
    """`WP-3B-15` ⑦ — the confirm is the sole release, and it needs an issue first."""
    session.engage_safety_latch(_stop_reason(at=0.0))

    session.deadman.request_rearm()
    session.deadman.confirm_rearm()

    assert not session.latch_active


def test_a_tick_after_the_lease_lapsed_latches(session: ArmSession, clock: ManualClock) -> None:
    """The tick is what gives the deadman a chance to notice.

    Without a caller for `poll`, expiry is a fact the process holds and never acts on — which is
    the shape every other unwired symbol in this repository has had.

    The live tick before the lapse is not padding. `DeadmanMonitor` latches on the transition
    from live to expired rather than on the level, so a loop that never observed the lease live
    has no edge to fall from — and a test that skipped it would pass against a session that
    polled nothing.
    """
    session.deadman.receive_renewal(
        LeaseRenewal(
            generation=session.deadman.current_generation,
            sequence=1,
            issued_mono_client=clock.now(),
        )
    )
    session.tick()
    assert not session.latch_active

    clock.advance(DEADMAN_LEASE_DURATION_SEC * 2)
    session.tick()

    assert session.latch_active


def test_both_arms_are_read_and_published_on_one_tick(clock: ManualClock) -> None:
    """Two sides, one tick, two boards — and neither side's frame lands on the other's board.

    A single board shared by two followers is the arrangement `ArmStateBoard` names in its own
    docstring: they would judge each other's arm, and a reader asking about the right arm would
    be answered about the left.
    """
    left, right = RecordingArm(clock), RecordingArm(clock)
    session = ArmSession(clock=clock, read_arms={LEFT: left.read, RIGHT: right.read})

    session.tick()

    assert session.sides == (LEFT, RIGHT)
    assert (left.reads, right.reads) == (1, 1)
    assert session.board(LEFT).view().state is not session.board(RIGHT).view().state


def test_each_side_is_stamped_when_its_own_read_finished(clock: ManualClock) -> None:
    """One timestamp for both arms would hide the gap the second read actually cost."""
    left, right = RecordingArm(clock), RecordingArm(clock)
    session = ArmSession(clock=clock, read_arms={LEFT: left.read, RIGHT: right.read})

    session.tick()

    first = session.board(LEFT).view().state
    second = session.board(RIGHT).view().state
    assert first is not None
    assert second is not None
    assert second.read_at - first.read_at == READ_DURATION_SEC


def test_a_session_over_no_arm_is_refused() -> None:
    """A session that reads nothing ticks, latches and publishes nothing — an idle-looking rig."""
    with pytest.raises(ValueError, match="at least one side"):
        ArmSession(clock=ManualClock(), read_arms={})


def _stop_reason(at: float) -> LatchReason:
    """A latch attribution standing in for the GUI soft stop."""
    return LatchReason(
        gate_id="test:stop",
        previous_state="RUNNING",
        new_state="SAFETY_LATCH_HOLD",
        latched_at=at,
    )
