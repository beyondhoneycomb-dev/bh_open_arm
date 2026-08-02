"""The two-channel single writer: which channel each half reaches, and which slots go nowhere.

Every mistake this writer can make is the same length and the same count as correct behaviour.
Swapping the halves sends sixteen commands to two channels either way. Permuting a half sends
eight. Emitting the unfitted slot sends one more frame than it should on a channel that would
have accepted it. None of those change a call count, so nothing here asserts one: what is
asserted is which motor name received which slot's angle on which bus.

Every slot in a test emission carries a distinct angle and a distinct torque. With a uniform
emission a swapped half and a permuted half both produce byte-identical frames, and the three
refusals below would be untestable.

The scheduler's per-tick guard reads the writer's own counter, so the two mis-counting stand-ins
are here as violation fixtures: a fan-out that counts per channel and one whose counter never
moves. Without them "one tick is one write" is a claim about a writer that happens to be right.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from backend.actuation import (
    BIMANUAL_BATCH_WIDTH,
    ActuationScheduler,
    ArmWriteSlots,
    BimanualCanWriter,
    BusCanWriter,
    EmissionInvariantError,
    LeaseManager,
    MailboxProducer,
    ManualClock,
    TargetMailbox,
    TickTrace,
)
from backend.calibration.schema import MOTOR_ORDER
from contracts.action import ExecutedMitCommand
from contracts.units import Nm, Rad, RadPerSec

# The angle and torque step between adjacent slots of a test emission. Synthetic — no rig
# reported these; what matters is only that all sixteen slots differ, so a half that landed on
# the wrong channel or in the wrong order is visible in the frame rather than indistinguishable.
SYNTHETIC_SLOT_STEP_RAD = 0.01
SYNTHETIC_SLOT_STEP_NM = 0.5

# Gains a test emission carries. Constant across slots deliberately: they are passed through
# untouched, so a per-slot value here would assert the loop index rather than the pass-through.
SYNTHETIC_KP = 40.0
SYNTHETIC_KD = 1.0

# A velocity every command in these emissions carries. Zero because every accepted command does
# (`positions_to_batch`), and because a non-zero value would make the rad/s-to-deg/s crossing the
# only thing the velocity slot could be asserting.
STILL_DQ_RAD_S = RadPerSec(0.0)

# The layout slot the spatula build puts no motor behind: nothing answers on `0x08`.
UNFITTED_SLOT_NAME = MOTOR_ORDER[-1]

# Slots per arm, and the two arms of the emission this rig commands.
ARM_SLOT_WIDTH = len(MOTOR_ORDER)
ARM_COUNT = BIMANUAL_BATCH_WIDTH // ARM_SLOT_WIDTH

# Index inside a half used when the skipped slot must not be the last one. A trailing `None` is
# also what a truncating writer produces, so the interior case is what separates the two.
INTERIOR_SLOT_INDEX = 3

# Degrees per radian, for the crossing the bus API expects. Written out rather than imported from
# the conversion under test: a test that converts with the same function it is judging agrees
# with itself whatever that function does.
DEG_PER_RAD = 57.29577951308232

# Agreement tolerance for a radian-to-degree crossing.
ANGLE_TOLERANCE_DEG = 1e-9

# Where a real capture of the first live two-channel engage is read from, and why it is not here.
FIXTURE_ENV_VAR = "OPENARM_TORQUE_BRINGUP_REAL_FIXTURE"
_SKIP_REASON = (
    "the first frame this writer puts on two real channels: one person supporting a brakeless "
    "arm, both channels bound and powered, and ./scripts/torque_session.sh --run driving it "
    "(12 FR-SAF-075, 16 M-2). Nothing offline can stand in for it — the two arms are "
    "indistinguishable on the bus, so only a person watching which arm moved can confirm the "
    "left half reached the left arm; set "
    f"{FIXTURE_ENV_VAR} to a real capture directory to re-verify"
)


class _RecordingMitBus:
    """One channel that records every batch it was sent, and can be told to raise.

    Attributes:
        sent: One entry per MIT write, each the command dict that write carried.
    """

    def __init__(self) -> None:
        """Build a bus with an empty log and no armed fault."""
        self.sent: list[dict[str, tuple[float, float, float, float, float]]] = []
        self.fault: Exception | None = None

    def _mit_control_batch(
        self, commands: dict[str, tuple[float, float, float, float, float]]
    ) -> None:
        """Record one batch, or raise the armed fault instead of recording it."""
        if self.fault is not None:
            raise self.fault
        self.sent.append(dict(commands))


class _PerChannelCountingWriter:
    """A fan-out that counts one write per channel instead of one per emission.

    The violation fixture for the single-write guard: it delegates the whole split to the
    production writer, so the only thing wrong with it is the number the scheduler reads.
    """

    def __init__(self, arms: tuple[ArmWriteSlots, ...]) -> None:
        """Wrap a production writer and add a second count per call."""
        self._writer = BimanualCanWriter(arms)
        self._per_channel_extra = 0

    @property
    def write_count(self) -> int:
        """The inflated tally: one per emission plus one per further channel."""
        return self._writer.write_count + self._per_channel_extra

    def mit_control_batch(self, batch: tuple[ExecutedMitCommand, ...]) -> None:
        """Fan out through the production writer, then count the second channel again."""
        self._writer.mit_control_batch(batch)
        self._per_channel_extra += ARM_COUNT - 1


class _UncountedWriter:
    """A fan-out whose counter never moves — a writer that sends and reports nothing.

    The other half of the guard's fixture pair. A scheduler that trusted its own bookkeeping
    instead of the writer's would see a write here where the bus saw one and the count did not.
    """

    def __init__(self, arms: tuple[ArmWriteSlots, ...]) -> None:
        """Wrap a production writer and hide its tally."""
        self._writer = BimanualCanWriter(arms)

    @property
    def write_count(self) -> int:
        """Always zero, whatever reached the channels."""
        return 0

    def mit_control_batch(self, batch: tuple[ExecutedMitCommand, ...]) -> None:
        """Fan out through the production writer without reporting it."""
        self._writer.mit_control_batch(batch)


def _spatula_slot_names() -> tuple[str | None, ...]:
    """One arm's half as the fitted spatula build masks it: the layout order, no `0x08`."""
    return tuple(None if name == UNFITTED_SLOT_NAME else name for name in MOTOR_ORDER)


def _distinct_batch() -> tuple[ExecutedMitCommand, ...]:
    """One full emission whose every slot carries an angle and a torque no other slot does."""
    return tuple(
        ExecutedMitCommand(
            kp=SYNTHETIC_KP,
            kd=SYNTHETIC_KD,
            q=Rad(SYNTHETIC_SLOT_STEP_RAD * (index + 1)),
            dq=STILL_DQ_RAD_S,
            tau=Nm(SYNTHETIC_SLOT_STEP_NM * (index + 1)),
        )
        for index in range(BIMANUAL_BATCH_WIDTH)
    )


def _two_arm_plan(
    slot_names: tuple[str | None, ...] | None = None,
) -> tuple[tuple[ArmWriteSlots, ...], tuple[_RecordingMitBus, ...]]:
    """A plan over two recording channels, both halves masked the same way.

    Args:
        slot_names: The half to give both arms; the spatula mask otherwise.

    Returns:
        (tuple, tuple) The plan and the buses behind it, in the same arm-major order.
    """
    names = _spatula_slot_names() if slot_names is None else slot_names
    buses = tuple(_RecordingMitBus() for _ in range(ARM_COUNT))
    plan = tuple(ArmWriteSlots(bus=bus, slot_names=names) for bus in buses)
    return plan, buses


# --- One emission, one counted write, each half on its own channel ---


def test_one_emission_is_one_counted_write_over_two_channels() -> None:
    """A fan-out is one write, not one per channel: the scheduler's guard reads this counter."""
    plan, buses = _two_arm_plan()
    writer = BimanualCanWriter(plan)

    writer.mit_control_batch(_distinct_batch())

    assert writer.write_count == 1
    assert [len(bus.sent) for bus in buses] == [1] * ARM_COUNT


def test_each_half_reaches_its_own_channel_and_no_other() -> None:
    """The first half goes to the first declared arm's bus, the second to the second's.

    Nothing on the bus tells the arms apart — both answer on send ids `0x01–0x08` — so the arm
    order of the plan is the only statement of which half is which, and a swap is a commanded
    jump rather than a detected error. The two halves carry different angles here, so a swap
    lands as a wrong angle rather than as an identical frame.
    """
    plan, buses = _two_arm_plan()
    batch = _distinct_batch()

    BimanualCanWriter(plan).mit_control_batch(batch)

    for arm_index, bus in enumerate(buses):
        offset = arm_index * ARM_SLOT_WIDTH
        for slot_index, name in enumerate(plan[arm_index].slot_names):
            if name is None:
                continue
            expected = batch[offset + slot_index]
            assert bus.sent[0][name][2] == pytest.approx(
                expected.q.value * DEG_PER_RAD, abs=ANGLE_TOLERANCE_DEG
            )
            assert bus.sent[0][name][4] == expected.tau.value


def test_the_halves_are_not_interchangeable() -> None:
    """Declaring the arms in the other order sends the other half to each channel.

    The point of the case is that both orders are accepted and produce full, well-formed frames
    on both channels. Nothing downstream can tell them apart, so the assertion is that the
    frames differ — which is what makes the plan's arm order load-bearing.
    """
    forward_plan, forward_buses = _two_arm_plan()
    swapped_plan = tuple(reversed(forward_plan))
    batch = _distinct_batch()

    BimanualCanWriter(forward_plan).mit_control_batch(batch)
    BimanualCanWriter(swapped_plan).mit_control_batch(batch)

    first_fitted = MOTOR_ORDER[0]
    # The swapped writer's own first arm is the forward plan's second channel, so the second
    # channel now holds what the first one holds under the forward order.
    assert forward_buses[0].sent[0][first_fitted] == forward_buses[1].sent[1][first_fitted]
    assert forward_buses[0].sent[0][first_fitted] != forward_buses[1].sent[0][first_fitted]


def test_slot_order_inside_a_half_is_the_order_the_plan_declares() -> None:
    """A permuted half is the same width and the same count, and puts one joint on another.

    The writer addresses the layout by index, so the plan's order is the whole statement of
    which slot is which joint. Reversing one arm's half must therefore change what each named
    motor is commanded to, and the frame is otherwise indistinguishable.
    """
    straight_plan, straight_buses = _two_arm_plan()
    reversed_names = tuple(reversed(_spatula_slot_names()))
    permuted_plan, permuted_buses = _two_arm_plan(reversed_names)
    batch = _distinct_batch()

    BimanualCanWriter(straight_plan).mit_control_batch(batch)
    BimanualCanWriter(permuted_plan).mit_control_batch(batch)

    straight = straight_buses[0].sent[0]
    permuted = permuted_buses[0].sent[0]
    assert sorted(straight) == sorted(permuted)
    assert straight[MOTOR_ORDER[0]] != permuted[MOTOR_ORDER[0]]


# --- The slot nothing answers on ---


def test_an_unfitted_slot_produces_no_frame() -> None:
    """`0x08` answered 0 of 20 polls on both arms; sixteen unanswered frames went ERROR-PASSIVE."""
    plan, buses = _two_arm_plan()

    BimanualCanWriter(plan).mit_control_batch(_distinct_batch())

    fitted = [name for name in MOTOR_ORDER if name != UNFITTED_SLOT_NAME]
    for bus in buses:
        assert sorted(bus.sent[0]) == sorted(fitted)
        assert UNFITTED_SLOT_NAME not in bus.sent[0]


def test_an_unfitted_slot_in_the_middle_shifts_nothing_after_it() -> None:
    """The skip is per slot, not a truncation: a later joint keeps its own slot's angle.

    A writer that dropped the unfitted slot from the *batch* rather than from the *frame* would
    pass every case whose gap is the last slot, and would command joint 5 with joint 4's angle
    the moment the gap moved.
    """
    names = list(_spatula_slot_names())
    absent = names[INTERIOR_SLOT_INDEX]
    names[INTERIOR_SLOT_INDEX] = None
    plan, buses = _two_arm_plan(tuple(names))
    batch = _distinct_batch()

    BimanualCanWriter(plan).mit_control_batch(batch)

    assert absent not in buses[0].sent[0]
    for slot_index, name in enumerate(names):
        if name is None:
            continue
        assert buses[0].sent[0][name][2] == pytest.approx(
            batch[slot_index].q.value * DEG_PER_RAD, abs=ANGLE_TOLERANCE_DEG
        )


# --- The plan the writer refuses to be built from ---


def test_a_plan_that_does_not_cover_the_emission_is_refused() -> None:
    """A narrower plan leaves joints uncommanded; a wider one is addressed past the frame's end."""
    short = _spatula_slot_names()[:-1]
    with pytest.raises(ValueError, match="one emission is"):
        BimanualCanWriter(_two_arm_plan(short)[0])


def test_unequal_halves_are_refused_even_when_the_total_is_right() -> None:
    """The split is at a fixed index per arm, so unequal halves misaddress a correct total."""
    names = _spatula_slot_names()
    lopsided = (
        ArmWriteSlots(bus=_RecordingMitBus(), slot_names=names[:-1]),
        ArmWriteSlots(bus=_RecordingMitBus(), slot_names=(*names, names[0])),
    )
    assert sum(len(arm.slot_names) for arm in lopsided) == BIMANUAL_BATCH_WIDTH
    with pytest.raises(ValueError, match="unequal halves"):
        BimanualCanWriter(lopsided)


def test_an_arm_with_no_fitted_motor_is_refused() -> None:
    """A write for it would count as the tick's one write and put no frame on that channel."""
    empty = tuple(None for _ in MOTOR_ORDER)
    plan = (
        ArmWriteSlots(bus=_RecordingMitBus(), slot_names=_spatula_slot_names()),
        ArmWriteSlots(bus=_RecordingMitBus(), slot_names=empty),
    )
    with pytest.raises(ValueError, match="no fitted motor"):
        BimanualCanWriter(plan)


def test_a_half_that_names_one_motor_twice_is_refused() -> None:
    """A bus batch is keyed by name, so the later slot silently overwrites the earlier one."""
    names = list(_spatula_slot_names())
    names[INTERIOR_SLOT_INDEX] = names[0]
    with pytest.raises(ValueError, match="names a motor twice"):
        BimanualCanWriter(_two_arm_plan(tuple(names))[0])


def test_a_plan_with_no_arms_is_refused() -> None:
    """No channel to write on, and an emission that would be counted as written anyway."""
    with pytest.raises(ValueError, match="no arms"):
        BimanualCanWriter(())


def test_a_batch_that_does_not_match_the_plan_is_refused_at_the_send() -> None:
    """The width is checked per call too: the plan is fixed and the emission arrives each tick."""
    plan, buses = _two_arm_plan()
    writer = BimanualCanWriter(plan)

    with pytest.raises(ValueError, match="does not match"):
        writer.mit_control_batch(_distinct_batch()[:-1])

    assert writer.write_count == 0
    assert [bus.sent for bus in buses] == [[]] * ARM_COUNT


# --- The units the bus API takes ---


def test_the_frame_carries_the_same_tuple_the_one_channel_writer_would_send() -> None:
    """Both production writers cross the same fields, because they share one crossing.

    The two are the only things in the tree that turn an emitted command into a bus batch. If
    they disagreed about which fields cross a unit boundary, the frame that reaches a motor
    would depend on which writer the rig was assembled with — and the one-channel writer is the
    one whose crossing is pinned against the bus API by acceptance ⑱.
    """
    fitted = tuple(name for name in MOTOR_ORDER if name != UNFITTED_SLOT_NAME)
    batch = _distinct_batch()
    plan, fanout_buses = _two_arm_plan()
    single_bus = _RecordingMitBus()

    BimanualCanWriter(plan).mit_control_batch(batch)
    fitted_slice = tuple(batch[MOTOR_ORDER.index(name)] for name in fitted)
    BusCanWriter(single_bus, fitted).mit_control_batch(fitted_slice)

    assert fanout_buses[0].sent[0] == single_bus.sent[0]


def test_position_crosses_to_degrees_and_torque_stays_in_newton_metres() -> None:
    """The bus API takes degrees; the contract carries radians, and the torque crosses nothing."""
    plan, buses = _two_arm_plan()
    batch = _distinct_batch()

    BimanualCanWriter(plan).mit_control_batch(batch)

    kp, kd, position_deg, velocity_deg_s, tau_nm = buses[0].sent[0][MOTOR_ORDER[0]]
    assert kp == SYNTHETIC_KP
    assert kd == SYNTHETIC_KD
    assert position_deg == pytest.approx(batch[0].q.value * DEG_PER_RAD, abs=ANGLE_TOLERANCE_DEG)
    assert velocity_deg_s == pytest.approx(0.0)
    assert tau_nm == batch[0].tau.value


# --- A bus that raises part way through the fan-out ---


def test_a_channel_that_raises_mid_fanout_does_not_count_a_write() -> None:
    """The earlier arm is commanded and the later one is not, and the tick has to fail.

    The two sends are sequential on one thread, so there is no shape in which the second
    channel's failure un-sends the first channel's frame. What must not happen is the count
    advancing: a recorded write for a fan-out that half happened is a frame the record says
    reached both arms.
    """
    plan, buses = _two_arm_plan()
    fault = RuntimeError("the transmit buffer never drained")
    buses[-1].fault = fault
    writer = BimanualCanWriter(plan)

    with pytest.raises(RuntimeError, match="never drained"):
        writer.mit_control_batch(_distinct_batch())

    assert writer.write_count == 0
    assert len(buses[0].sent) == 1
    assert buses[-1].sent == []


# --- The writer is downstream of the gateway, not a second way onto a channel ---


def test_the_writer_surface_is_the_counter_and_the_batched_write_and_nothing_else() -> None:
    """A frame can only arrive here as an emission, so there is nothing else to expose.

    The emission the scheduler hands over came from a target the eight-stage filter passed. A
    method that took a position, a target or a raw frame would be a second way in, and it would
    be one the filter never saw — so the surface is the assertion.
    """
    surface = {name for name in dir(BimanualCanWriter) if not name.startswith("_")}

    assert surface == {"write_count", "mit_control_batch"}


def test_the_writer_holds_no_gateway_and_no_filter() -> None:
    """It carries the plan and the tally, and nothing that could decide anything."""
    plan, _buses = _two_arm_plan()

    held = vars(BimanualCanWriter(plan))

    assert set(held) == {"_arms", "_width", "_write_count"}


# --- The scheduler's single-write guard over this writer ---


def _scheduler_over(writer: object) -> tuple[ActuationScheduler, ManualClock]:
    """Stand a scheduler up on a writer, holding at the layout zero with a renewed lease."""
    clock = ManualClock()
    mailbox = TargetMailbox()
    lease = LeaseManager(BIMANUAL_BATCH_WIDTH)
    scheduler = ActuationScheduler(
        writer,  # type: ignore[arg-type]  # the stand-ins satisfy the protocol structurally
        mailbox,
        clock,
        lease,
        MailboxProducer("p", mailbox, clock),
        tuple(Rad(0.0) for _ in range(BIMANUAL_BATCH_WIDTH)),
        TickTrace(),
    )
    lease.renew(clock.now())
    return scheduler, clock


def test_one_tick_over_the_fanout_is_exactly_one_write() -> None:
    """The tick's guard is satisfied by the fan-out, and both channels received the frame."""
    plan, buses = _two_arm_plan()
    writer = BimanualCanWriter(plan)
    scheduler, _clock = _scheduler_over(writer)

    scheduler.tick()

    assert writer.write_count == 1
    assert [len(bus.sent) for bus in buses] == [1] * ARM_COUNT


def test_a_fanout_that_counts_per_channel_fails_the_tick() -> None:
    """Counting the second channel as a second write is what the guard exists to catch."""
    plan, _buses = _two_arm_plan()
    scheduler, _clock = _scheduler_over(_PerChannelCountingWriter(plan))

    with pytest.raises(EmissionInvariantError, match="exactly one CAN write"):
        scheduler.tick()


def test_a_fanout_whose_counter_never_moves_fails_the_tick() -> None:
    """A writer that sends and reports nothing is a dropped arm as far as the tick can tell."""
    plan, _buses = _two_arm_plan()
    scheduler, _clock = _scheduler_over(_UncountedWriter(plan))

    with pytest.raises(EmissionInvariantError, match="exactly one CAN write"):
        scheduler.tick()


# --- The deferred acceptance: the first two-channel frame on real hardware ---


class TwoChannelCaptureError(AssertionError):
    """Raised when a capture cannot answer which channel each arm's half went out on.

    An `AssertionError` deliberately: a supplied capture that carries no answer is a failed
    acceptance, not a configuration problem to skip past.
    """


def assert_capture_used_one_channel_per_arm(capture: dict, sides: tuple[str, ...]) -> None:
    """Refuse a capture whose engage did not put each arm's half on a channel of its own.

    The interfaces are the only record of the split that survives the session. Both arms answer
    on the same send ids, so a session that opened one channel twice writes sixteen commands
    that all reach one arm — the frame is well formed, every id is fitted, and the capture is
    self-consistent. Only the channel names separate that from a real bimanual write.

    Args:
        capture: One capture record.
        sides: The arm sides an engage must have recorded a channel for.

    Raises:
        TwoChannelCaptureError: If a side is missing, or two sides share a channel.
    """
    interfaces = capture.get("interfaces")
    if not isinstance(interfaces, dict):
        raise TwoChannelCaptureError(
            "the capture records no channel per arm, so which arm each half of the emission "
            "reached is not in it"
        )
    missing = [side for side in sides if not interfaces.get(side)]
    if missing:
        raise TwoChannelCaptureError(
            f"the capture records no channel for {missing}; an arm whose channel is unrecorded "
            "is an arm nothing says the writer addressed"
        )
    resolved = [interfaces[side] for side in sides]
    if len(set(resolved)) != len(resolved):
        raise TwoChannelCaptureError(
            f"the capture puts more than one arm on the same channel ({resolved}); both arms "
            "answer on send ids 0x01-0x08, so one channel written twice commands one arm with "
            "both halves and nothing on the bus reports it"
        )


def _capture_with(interfaces: dict[str, str]) -> dict:
    """A capture record carrying only the block this judgment reads."""
    return {"interfaces": dict(interfaces)}


def test_the_two_channel_judgment_accepts_one_channel_per_arm() -> None:
    assert_capture_used_one_channel_per_arm(
        _capture_with({"left": "can0", "right": "can1"}), ("left", "right")
    )


def test_the_two_channel_judgment_refuses_both_arms_on_one_channel() -> None:
    """The shape a single-bus writer produces: a full, self-consistent, one-armed capture."""
    with pytest.raises(TwoChannelCaptureError, match="same channel"):
        assert_capture_used_one_channel_per_arm(
            _capture_with({"left": "can0", "right": "can0"}), ("left", "right")
        )


def test_the_two_channel_judgment_refuses_a_capture_missing_an_arm() -> None:
    with pytest.raises(TwoChannelCaptureError, match="no channel for"):
        assert_capture_used_one_channel_per_arm(_capture_with({"left": "can0"}), ("left", "right"))


def test_the_two_channel_judgment_refuses_a_capture_with_no_interfaces_at_all() -> None:
    with pytest.raises(TwoChannelCaptureError, match="no channel per arm"):
        assert_capture_used_one_channel_per_arm({}, ("left", "right"))


def _real_fixture() -> Path | None:
    """The real capture directory named by the environment, if it is set and present."""
    raw = os.environ.get(FIXTURE_ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


_REAL_FIXTURE = _real_fixture()


@pytest.mark.skipif(
    _REAL_FIXTURE is None, reason="two-channel engage over real channels: " + _SKIP_REASON
)
def test_deferred_real_engage_used_one_channel_per_arm() -> None:
    """The first live run of this writer, judged on what the session recorded about it."""
    from backend.endeffector import SIDES

    assert _REAL_FIXTURE is not None
    captures = sorted(_REAL_FIXTURE.glob("*.json"))
    assert captures, f"{_REAL_FIXTURE} holds no capture to judge"
    for path in captures:
        assert_capture_used_one_channel_per_arm(json.loads(path.read_text(encoding="utf-8")), SIDES)
