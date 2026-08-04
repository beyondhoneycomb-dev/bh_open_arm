"""FR-MOT-058 ② on the Freedrive path — a stalled producer stops pushing the hands on the arm.

Freedrive is the gravity-compensated path: a person holds the arm and guides it by hand, and the
feed-forward torque on every joint is the arm's own weight held up for them. That torque stands
until a frame replaces it. So a producer that stalls mid-session leaves the last computed weight
pushing against the guide, against a pose the arm has since been moved out of, with nothing
measuring how long — unless the silence before each frame is what the gateway's FRESHNESS stage
judges. Passing a constant zero there leaves the stage running on every frame and unable to fire.

The exit is a powered hold, never a torque cut. `04` §2 states this arm carries no mechanical
brake, so cutting torque is dropping it onto whoever is holding it. A lapsed frame therefore
leaves Freedrive to the Cat-2 position hold, and what that hold carries is read off the writer
that emits it: one MIT batch with the hold stiffness, the restored damping and zero tau.

That the other outcome is unreachable is a second claim, and no bus double can carry it here.
Neither the session nor the producer holds a bus handle — the frame they yield is a value object
the caller hands to the single writer — so there is nothing a test can hand them and afterwards ask
whether it was disabled. The tree-wide half of that claim is `test_single_gateway.py`, which scans
this tree for the symbol; what is left for this file is the one object on the path that does touch a
bus, the writer the hold frame is emitted through, and it offers no way to reach the torque cut a
real bus has.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")

from backend.actuation.bus_writer import BusCanWriter
from backend.actuation.clock import ManualClock
from backend.actuation.config import MIT_HOLD_KD, MIT_HOLD_KP
from backend.actuation.enforcement import ActuationGateway
from backend.actuation.guard import CollisionGuard, GuardSample
from backend.actuation.safety import SafetyFilter, SafetyReason
from backend.deadman.constants import DEADMAN_LEASE_DURATION_SEC
from backend.freedrive import (
    FRICTION_PASSED_STATUS,
    FreedriveSession,
    FrictionGate,
    HoldCause,
    TickMode,
    friction_gate_status,
)
from backend.freedrive.constants import (
    DEFAULT_KD_FREEDRIVE,
    FREEDRIVE_CONTROL_PERIOD_SEC,
    FREEDRIVE_FRESHNESS_WINDOW_SEC,
)
from backend.freedrive.producer import FreedriveProducer
from tests.wp2d03._support import (
    ENTRY_POSE_RAD,
    ENTRY_VELOCITY_RAD_S,
    arm_safety_limits,
    friction_seed,
    gravity_backend,
)

# The gaps that bracket the window, stated absolutely rather than as `window +- epsilon`: a case
# phrased in the constant it pins moves wherever that constant moves and admits any widening.
LAST_LIVE_GAP_SEC = 0.050
FIRST_STALE_GAP_SEC = 0.051

# The silence every stall case below advances by. It has to be the producer's and nothing else's:
# past FREEDRIVE_FRESHNESS_WINDOW_SEC, so the gateway calls the source stale, and not past
# DEADMAN_LEASE_DURATION_SEC, or the tick exits on a lapsed lease and the hold it produces says
# nothing about a producer at all. The band those two leave is narrow and this value sits near its
# top, so it is the lease bound a change to either constant breaks first. The relation is held by
# a case below rather than stated here, because a relation stated in a comment is one nobody checks.
LONG_STALL_SEC = 0.09

# One MIT batch is what a Cat-2 hold is (`04` NFR-MAN-002): the stop path sends a hold frame,
# never a torque disable.
CAT2_HOLD_BATCH_COUNT = 1

NO_FEEDFORWARD_TORQUE_NM = 0.0


class RecordingMitBus:
    """A CAN-free MIT bus double that records batches and refuses to be disabled.

    It offers `disable_torque` on purpose. A real `DamiaoMotorsBus` has it, so a double without it
    would make the writer's inability to cut torque a property of the fixture instead of a property
    of the writer; the case that checks the writer needs the capability to actually be there behind
    it. Reaching it is the failure itself, not something to tally afterwards.
    """

    def __init__(self) -> None:
        """Start with nothing sent."""
        self.batches: list[dict[str, tuple[float, float, float, float, float]]] = []

    def _mit_control_batch(
        self, commands: dict[str, tuple[float, float, float, float, float]]
    ) -> None:
        """Record one batch; no CAN, no motor."""
        self.batches.append(commands)

    def disable_torque(self) -> None:
        """Fail the case outright: on a brakeless arm this is the arm falling onto the operator.

        Raises:
            AssertionError: Always. Nothing on the Freedrive exit path may reach this.
        """
        raise AssertionError(
            "the Freedrive exit cut torque instead of holding; this arm has no mechanical brake, "
            "so that is the arm dropping onto the hands guiding it (04 NFR-MAN-002)"
        )


def _producer(clock: ManualClock) -> FreedriveProducer:
    """Build a Freedrive producer over a healthy envelope and the given clock."""
    gateway = ActuationGateway(
        safety_filter=SafetyFilter(arm_safety_limits()),
        guard=CollisionGuard(on_latch=_ignore_latch, clock=clock),
        dt_sec=FREEDRIVE_CONTROL_PERIOD_SEC,
        freshness_window_sec=FREEDRIVE_FRESHNESS_WINDOW_SEC,
    )
    return FreedriveProducer(
        gravity_backend(),
        friction_seed(),
        gateway,
        tuple(DEFAULT_KD_FREEDRIVE for _ in ENTRY_POSE_RAD),
        clock,
    )


def _engaged_session(clock: ManualClock) -> FreedriveSession:
    """Build a session past the friction gate, held and entered at the entry pose."""
    gate = FrictionGate(friction_gate_status(FRICTION_PASSED_STATUS))
    session = FreedriveSession(gravity_backend(), friction_seed(), arm_safety_limits(), gate, clock)
    session.hold_heartbeat()
    session.enter(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S, GuardSample.healthy())
    return session


def _ignore_latch(reason) -> None:  # noqa: ANN001
    """A no-op latch sink for a gateway these cases drive with healthy poses only."""


def _frame(producer: FreedriveProducer):  # noqa: ANN202
    """Produce one frame at the entry pose."""
    return producer.produce_frame(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S, GuardSample.healthy())


def _motor_names() -> tuple[str, ...]:
    """The arm's motor names in batch-index order, the width the writer checks a batch against."""
    return tuple(f"joint_{index + 1}" for index in range(len(ENTRY_POSE_RAD)))


def test_the_first_frame_of_a_session_is_not_stale() -> None:
    """Nothing preceded the opening frame, so it is not late — refusing it would never engage."""
    frame = _frame(_producer(ManualClock()))

    assert frame.engaged is True
    assert frame.hold_reason is None


def test_a_producer_keeping_its_period_stays_engaged() -> None:
    """A producer running at its declared control period is never stale."""
    clock = ManualClock()
    producer = _producer(clock)

    _frame(producer)
    clock.advance(FREEDRIVE_CONTROL_PERIOD_SEC)
    frame = _frame(producer)

    assert frame.engaged is True


def test_a_fifty_millisecond_gap_is_the_last_one_served() -> None:
    """Where the window sits, as a number: 50 ms of silence still drives the hand-guided arm."""
    clock = ManualClock()
    producer = _producer(clock)

    _frame(producer)
    clock.advance(LAST_LIVE_GAP_SEC)
    frame = _frame(producer)

    assert frame.engaged is True


def test_a_fifty_one_millisecond_gap_is_the_first_one_refused() -> None:
    """One millisecond past the window the producer is stale and commands nothing.

    The refusal edge is where a widened window hides: at twice the real value every admissible
    case here still passes, and the gravity torque keeps standing against the operator's hands.
    """
    clock = ManualClock()
    producer = _producer(clock)

    _frame(producer)
    clock.advance(FIRST_STALE_GAP_SEC)
    frame = _frame(producer)

    assert frame.engaged is False
    assert frame.hold_reason is SafetyReason.STALE_SOURCE
    assert frame.commands == ()


def test_the_stalled_frame_carries_no_feedforward_torque() -> None:
    """The frame after a stall feeds nothing forward, whatever gravity asked for.

    The gravity term itself is still reported — the pose has weight either way — so the case
    that matters is the accepted feed-forward, which is what would have reached the joint.
    """
    clock = ManualClock()
    producer = _producer(clock)

    _frame(producer)
    clock.advance(LONG_STALL_SEC)
    frame = _frame(producer)

    assert all(value == NO_FEEDFORWARD_TORQUE_NM for value in frame.feedforward_nm)
    assert any(value != NO_FEEDFORWARD_TORQUE_NM for value in frame.tau_grav_nm)


def test_the_producer_is_live_again_on_the_frame_after_the_stall() -> None:
    """The hold is one frame's verdict, not a latch — a producer that resumes is served again."""
    clock = ManualClock()
    producer = _producer(clock)

    _frame(producer)
    clock.advance(LONG_STALL_SEC)
    assert _frame(producer).engaged is False
    clock.advance(FREEDRIVE_CONTROL_PERIOD_SEC)

    assert _frame(producer).engaged is True


def test_the_stall_the_exit_cases_use_isolates_the_producer_from_the_lease() -> None:
    """The stall must clear the freshness window and stay inside the lease, or it tests the lease.

    Both bounds are owned elsewhere — the window by the actuation spine, the lease by the deadman —
    and either can move without this file noticing. Under the window the producer is still live and
    no case exits at all; past the lease every exit case below becomes a deadman timeout that would
    pass its `TickMode.HOLD` assertion while proving nothing about a stalled producer.
    """
    assert LONG_STALL_SEC > FREEDRIVE_FRESHNESS_WINDOW_SEC
    assert LONG_STALL_SEC <= DEADMAN_LEASE_DURATION_SEC


def test_a_stalled_session_exits_to_a_powered_hold_rather_than_dropping_torque() -> None:
    """The stall exits Freedrive through the Cat-2 hold, and the emitted frame is a powered one.

    On an arm with no mechanical brake a disable and a hold both stop the motion, and the session
    return value alone cannot separate them. What separates them is the frame that reaches the bus:
    one MIT batch carrying the hold stiffness, the restored damping and zero tau.
    """
    clock = ManualClock()
    session = _engaged_session(clock)
    clock.advance(LONG_STALL_SEC)

    tick = session.tick(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S, GuardSample.healthy())

    assert tick.mode is TickMode.HOLD
    assert tick.exit is not None
    assert tick.exit.cause is HoldCause.GATEWAY_HOLD
    assert tick.frame is not None
    assert tick.frame.hold_reason is SafetyReason.STALE_SOURCE

    bus = RecordingMitBus()
    BusCanWriter(bus, _motor_names()).mit_control_batch(tick.exit.hold_commands)

    assert len(bus.batches) == CAT2_HOLD_BATCH_COUNT
    for kp, kd, _position, _velocity, tau in bus.batches[0].values():
        assert kp == MIT_HOLD_KP
        assert kd == MIT_HOLD_KD
        assert tau == NO_FEEDFORWARD_TORQUE_NM


def test_the_writer_the_hold_frame_is_emitted_through_cannot_cut_torque() -> None:
    """The bus behind the writer can drop torque and the writer gives no way to ask for it.

    The session and the producer hold no bus handle, so the only object on the Freedrive exit path
    that touches a bus at all is this writer, and what makes the exit a hold rather than a fall is
    that its surface carries no torque cut (`backend/actuation/bus_writer.py` says so deliberately).
    The double is checked for the capability first, so the writer's lack of it is the writer's and
    not the fixture's.
    """
    bus = RecordingMitBus()

    writer = BusCanWriter(bus, _motor_names())

    assert hasattr(bus, "disable_torque")
    assert not hasattr(writer, "disable_torque")
