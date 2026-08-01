"""FR-MOT-058 ② on the Freedrive path — a stalled producer stops pushing the hands on the arm.

Freedrive is the gravity-compensated path: a person holds the arm and guides it by hand, and the
feed-forward torque on every joint is the arm's own weight held up for them. That torque stands
until a frame replaces it. So a producer that stalls mid-session leaves the last computed weight
pushing against the guide, against a pose the arm has since been moved out of, with nothing
measuring how long — unless the silence before each frame is what the gateway's FRESHNESS stage
judges. Passing a constant zero there leaves the stage running on every frame and unable to fire.

The exit is a powered hold, never a torque cut. `04` §2 states this arm carries no mechanical
brake, so cutting torque is dropping it onto whoever is holding it. A lapsed frame therefore
leaves Freedrive to the Cat-2 position hold, and the case below proves that through a real bus
double: one MIT batch with the hold stiffness, the restored damping and zero tau, and the bus's
disable counter still at zero.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")

from backend.actuation.bus_writer import BusCanWriter
from backend.actuation.clock import ManualClock
from backend.actuation.config import MIT_HOLD_KD, MIT_HOLD_KP
from backend.actuation.enforcement import ActuationGateway
from backend.actuation.guard import CollisionGuard
from backend.actuation.safety import SafetyFilter, SafetyReason
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

# A silence no plausible window admits — fifty control periods — and still well inside the
# deadman lease, so what the tick exits on is the stale producer and not a lapsed lease.
LONG_STALL_SEC = 0.09

# One MIT batch is what a Cat-2 hold is (`04` NFR-MAN-002): the stop path sends a hold frame,
# never a torque disable.
CAT2_HOLD_BATCH_COUNT = 1

NO_FEEDFORWARD_TORQUE_NM = 0.0


class RecordingMitBus:
    """A CAN-free MIT bus double that counts batches and torque disables separately.

    The two counters are the point. A returned frame cannot tell a powered hold from a dropped
    arm — both stop the motion — so the only witness is what reached the bus: a hold frame, or
    a `disable_torque` that on a brakeless arm is the arm falling onto the operator's hands.
    """

    def __init__(self) -> None:
        """Start with nothing sent and nothing disabled."""
        self.batches: list[dict[str, tuple[float, float, float, float, float]]] = []
        self.disable_calls = 0

    def _mit_control_batch(
        self, commands: dict[str, tuple[float, float, float, float, float]]
    ) -> None:
        """Record one batch; no CAN, no motor."""
        self.batches.append(commands)

    def disable_torque(self) -> None:
        """Count a torque drop, so a test can assert none happened."""
        self.disable_calls += 1


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
    session.enter(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S)
    return session


def _ignore_latch(reason) -> None:  # noqa: ANN001
    """A no-op latch sink for a gateway these cases drive with healthy poses only."""


def _frame(producer: FreedriveProducer):  # noqa: ANN202
    """Produce one frame at the entry pose."""
    return producer.produce_frame(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S)


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


def test_a_stalled_session_exits_to_a_powered_hold_rather_than_dropping_torque() -> None:
    """The stall exits Freedrive through the Cat-2 hold, and the bus double proves it was powered.

    On an arm with no mechanical brake a disable and a hold both stop the motion, and the session
    return value alone cannot separate them. What separates them is what reached the bus: one MIT
    frame carrying the hold stiffness, the restored damping and zero tau, with the disable counter
    untouched.
    """
    clock = ManualClock()
    session = _engaged_session(clock)
    clock.advance(LONG_STALL_SEC)

    tick = session.tick(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S)

    assert tick.mode is TickMode.HOLD
    assert tick.exit is not None
    assert tick.exit.cause is HoldCause.GATEWAY_HOLD
    assert tick.frame is not None
    assert tick.frame.hold_reason is SafetyReason.STALE_SOURCE

    bus = RecordingMitBus()
    motors = tuple(f"joint_{index + 1}" for index in range(len(ENTRY_POSE_RAD)))
    BusCanWriter(bus, motors).mit_control_batch(tick.exit.hold_commands)

    assert len(bus.batches) == CAT2_HOLD_BATCH_COUNT
    assert bus.disable_calls == 0
    for kp, kd, _position, _velocity, tau in bus.batches[0].values():
        assert kp == MIT_HOLD_KP
        assert kd == MIT_HOLD_KD
        assert tau == NO_FEEDFORWARD_TORQUE_NM
