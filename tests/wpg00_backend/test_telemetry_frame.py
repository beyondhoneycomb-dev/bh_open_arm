"""What the `telemetry` frame carries, and what it refuses to invent.

The frame had zero fields for as long as nothing read the arm. Two consumers were written against
it anyway and they want different things — `S-03` reads per-motor diagnostics, the policy path
reads the frozen 48-channel observation vector — so a frame serving one and not the other would
have made one of those screens permanently wrong.

Both are affordable because they come off one bus refresh: `sync_read_all_states` fills position,
velocity, torque and both temperatures in the cycle the pose arrives in. Nothing here costs a
frame the pose did not already cost.

The assertions that matter most are the absences. A board that published nothing, and a reader
with no thermometer, must not appear as zeros — a screen renders `0.0` and `0 °C` exactly like a
measurement, and this frame is the last place that distinction can still be made.
"""

from __future__ import annotations

from backend.actuation.board import ArmState, ArmStateBoard, ArmStateView
from backend.actuation.clock import ManualClock
from backend.actuation.guard import GuardSample
from backend.ws.dispatch import server_envelope
from backend.ws.telemetry import (
    ARM_BUS_READ_OK,
    ARM_READ_AGE,
    ARM_STALE,
    MOTOR_ROW_JOINT_NAME,
    MOTOR_ROW_TEMP_MOS,
    OBSERVATION_STATE_KEY,
    observation_vector,
    telemetry_body,
)
from contracts.plugin.robot_abc import raw_observation_channels
from contracts.units import Celsius, Deg, DegPerSec, Nm
from contracts.ws import (
    TELEMETRY_ARMS_FIELD,
    TELEMETRY_MOTOR_STATES_FIELD,
    TELEMETRY_OBSERVATION_FIELD,
)
from contracts.ws.schema import FRAME_TABLE, WsFrameType

# The frozen layout's width. Eight slots per side, seven joints and the gripper.
SLOTS_PER_SIDE = 8

# Distinct per channel and per side, so a vector assembled from the wrong tuple or the wrong arm
# fails rather than matching a repeated constant.
LEFT_POSE = tuple(Deg(float(index)) for index in range(SLOTS_PER_SIDE))
LEFT_VELOCITY = tuple(DegPerSec(float(index) + 0.5) for index in range(SLOTS_PER_SIDE))
LEFT_TORQUE = tuple(Nm(float(index) + 0.25) for index in range(SLOTS_PER_SIDE))
RIGHT_POSE = tuple(Deg(float(index) + 100.0) for index in range(SLOTS_PER_SIDE))
RIGHT_VELOCITY = tuple(DegPerSec(float(index) + 100.5) for index in range(SLOTS_PER_SIDE))
RIGHT_TORQUE = tuple(Nm(float(index) + 100.25) for index in range(SLOTS_PER_SIDE))

MOS_TEMPS = tuple(Celsius(40.0 + index) for index in range(SLOTS_PER_SIDE))
ROTOR_TEMPS = tuple(Celsius(30.0 + index) for index in range(SLOTS_PER_SIDE))

TICK = 7


def _state(
    pose: tuple[Deg, ...],
    velocity: tuple[DegPerSec, ...],
    torque: tuple[Nm, ...],
    *,
    thermometer: bool,
) -> ArmState:
    """One reading, with or without a temperature channel."""
    return ArmState(
        read_at=0.0,
        joint_deg=pose,
        torque_nm=torque,
        velocity_deg_s=velocity,
        temp_mos_c=MOS_TEMPS if thermometer else None,
        temp_rotor_c=ROTOR_TEMPS if thermometer else None,
        guard=GuardSample.healthy(),
        tick_index=TICK,
    )


# The deadline the frame judges an age against. Five control periods at the 100 Hz default, which
# is what `mount_websocket_router` computes from the rate the session is actually ticked at.
STALE_AFTER_SEC = 0.05


def _boards(
    *, thermometer: bool = True, publish: bool = True, age_s: float = 0.0
) -> dict[str, ArmStateBoard]:
    """Two published boards over one clock, as a session's would be.

    Args:
        thermometer: Whether the reader reports temperatures.
        publish: Whether either board has published at all.
        age_s: How far the clock is moved after publishing, which is how old every reading is
            when a view is taken — the whole difference between a live board and a dead loop.
    """
    clock = ManualClock()
    boards = {"left": ArmStateBoard(clock=clock), "right": ArmStateBoard(clock=clock)}
    if publish:
        boards["left"].publish(
            _state(LEFT_POSE, LEFT_VELOCITY, LEFT_TORQUE, thermometer=thermometer)
        )
        boards["right"].publish(
            _state(RIGHT_POSE, RIGHT_VELOCITY, RIGHT_TORQUE, thermometer=thermometer)
        )
    clock.advance(age_s)
    return boards


def _views(boards: dict[str, ArmStateBoard]) -> dict[str, ArmStateView]:
    """One view per board, taken together the way the sender takes them."""
    return {side: board.view() for side, board in boards.items()}


def test_the_body_carries_exactly_the_fields_the_contract_declares() -> None:
    """The envelope builder refuses anything else, so a drift here is a send that raises."""
    body = telemetry_body(_views(_boards()), STALE_AFTER_SEC)

    assert set(body) == set(FRAME_TABLE[WsFrameType.TELEMETRY].fields)


def test_the_envelope_accepts_the_body() -> None:
    """The two halves are written apart and only this runs them together.

    `server_envelope` compares the body against the contract's field tuple, so a body the
    builder produced and the contract does not admit fails at send time — on the live socket,
    with an arm energised, which is the worst place to find it.
    """
    envelope = server_envelope(
        WsFrameType.TELEMETRY, telemetry_body(_views(_boards()), STALE_AFTER_SEC)
    )

    assert envelope["type"] == WsFrameType.TELEMETRY.value


def test_the_observation_vector_is_the_frozen_channel_list_in_order() -> None:
    """One float per declared channel, positionally — this is what a policy eats.

    Checked against `raw_observation_channels` rather than a literal 48: the width is the
    contract's to state, and a test carrying its own copy would agree with a channel list that
    had drifted.
    """
    vector = observation_vector(_views(_boards()))

    assert len(vector) == len(list(raw_observation_channels(bimanual=True)))


def test_each_channel_reads_from_its_own_tuple() -> None:
    """`pos`, `vel` and `torque` come from three different board fields.

    The three are same-shaped float tuples, so a builder that transposed velocity and torque
    would produce a vector of the right width, in the right order, with the wrong numbers in it
    — and nothing downstream could tell.
    """
    vector = observation_vector(_views(_boards()))
    channels = [channel.name for channel in raw_observation_channels(bimanual=True)]
    reading = dict(zip(channels, vector, strict=True))

    assert reading["left_joint_1.pos"] == LEFT_POSE[0].value
    assert reading["left_joint_1.vel"] == LEFT_VELOCITY[0].value
    assert reading["left_joint_1.torque"] == LEFT_TORQUE[0].value


def test_the_two_arms_do_not_bleed_into_each_other() -> None:
    """A vector assembled from one side twice is the wrong arm's pose under the right name."""
    vector = observation_vector(_views(_boards()))
    channels = [channel.name for channel in raw_observation_channels(bimanual=True)]
    reading = dict(zip(channels, vector, strict=True))

    assert reading["left_joint_1.pos"] == LEFT_POSE[0].value
    assert reading["right_joint_1.pos"] == RIGHT_POSE[0].value


def test_a_thermometer_produces_one_row_per_motor() -> None:
    """The diagnostics half — what the observation vector has no channel for."""
    body = telemetry_body(_views(_boards(thermometer=True)), STALE_AFTER_SEC)
    rows = body[TELEMETRY_MOTOR_STATES_FIELD]

    assert len(rows) == 2 * SLOTS_PER_SIDE
    assert rows[0][MOTOR_ROW_JOINT_NAME] == "left_joint_1"
    assert rows[0][MOTOR_ROW_TEMP_MOS] == MOS_TEMPS[0].value


def test_a_reader_with_no_thermometer_reports_no_rows_rather_than_zeros() -> None:
    """A CAN-free double has no MOSFET, and `0 °C` renders exactly like a measurement.

    This is the whole reason the board's temperature is optional rather than a zeroed tuple:
    the absence has to survive as far as the wire, because the screen cannot recover it.
    """
    body = telemetry_body(_views(_boards(thermometer=False)), STALE_AFTER_SEC)

    assert body[TELEMETRY_MOTOR_STATES_FIELD] == []


def test_the_observation_vector_still_fills_when_there_is_no_thermometer() -> None:
    """Losing the diagnostics half must not cost the policy half — they are separate channels."""
    vector = observation_vector(_views(_boards(thermometer=False)))

    assert any(value != 0.0 for value in vector)


def test_a_board_that_published_nothing_contributes_no_arm_entry() -> None:
    """ "No reading yet" and "a reading that went stale" are different facts.

    Reported as an omission rather than an infinite age, so a client cannot render a server
    still starting up as an arm that died.
    """
    body = telemetry_body(_views(_boards(publish=False)), STALE_AFTER_SEC)

    assert body[TELEMETRY_ARMS_FIELD] == {}
    assert body[TELEMETRY_OBSERVATION_FIELD][OBSERVATION_STATE_KEY] == [
        0.0 for _ in raw_observation_channels(bimanual=True)
    ]


def test_the_guard_reaches_the_wire() -> None:
    """The badge bar's only possible source. Without it a stalled board reads as a still arm."""
    body = telemetry_body(_views(_boards()), STALE_AFTER_SEC)

    assert body[TELEMETRY_ARMS_FIELD]["left"][ARM_BUS_READ_OK] is True
    assert body[TELEMETRY_ARMS_FIELD]["left"][ARM_READ_AGE] == 0.0


def test_a_fresh_reading_is_not_stale() -> None:
    """The healthy case, which the two below are only meaningful against."""
    body = telemetry_body(_views(_boards()), STALE_AFTER_SEC)

    assert body[TELEMETRY_ARMS_FIELD]["left"][ARM_STALE] is False


def test_a_reading_past_the_deadline_is_reported_stale() -> None:
    """The failure this field exists for, and the one that already happened.

    A CAN adapter left the bus, the tick that fills these boards raised and returned, and the
    push loop kept sending this exact body at the full rate for forty-five minutes. Every value
    in it was a real measurement — of a moment three quarters of an hour earlier. The badge read
    `arms` non-empty and reported a connected arm the entire time.
    """
    body = telemetry_body(_views(_boards(age_s=STALE_AFTER_SEC * 2.0)), STALE_AFTER_SEC)

    assert body[TELEMETRY_ARMS_FIELD]["left"][ARM_STALE] is True
    assert body[TELEMETRY_ARMS_FIELD]["right"][ARM_STALE] is True


def test_the_stale_verdict_moves_with_the_deadline_it_was_given() -> None:
    """The deadline is the caller's, derived from the tick rate the session was built at.

    An operator who lowered `control_tick_hz` widened the interval a healthy board publishes at,
    and a verdict pinned to a figure chosen here would call that arm dead.
    """
    aged = _views(_boards(age_s=0.2))

    assert telemetry_body(aged, 0.05)[TELEMETRY_ARMS_FIELD]["left"][ARM_STALE] is True
    assert telemetry_body(aged, 0.5)[TELEMETRY_ARMS_FIELD]["left"][ARM_STALE] is False


def test_a_stale_reading_still_carries_its_age() -> None:
    """The verdict does not replace the number it was made from.

    An operator needs to know whether the reading stopped a second ago or an hour ago, and the
    boolean cannot say. Both travel.
    """
    body = telemetry_body(_views(_boards(age_s=1.5)), STALE_AFTER_SEC)

    assert body[TELEMETRY_ARMS_FIELD]["left"][ARM_READ_AGE] == 1.5
