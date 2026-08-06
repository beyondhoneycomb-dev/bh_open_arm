"""The wire: one command code goes out, and the frame that comes back is decoded whole.

Every test here exists because the tool's central claim is about what it puts on the bus. "It
never energizes the arm" is not a property of the docstring — it is a property of the bytes, and
the bytes are what these tests read.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.can.rid.motor_limits import MotorType
from backend.endeffector import ARM_JOINT_SEND_IDS, GRIPPER_SEND_ID
from contracts.units import Rad
from scripts import can_node_watch as watch
from scripts.can_node_watch_tests.watch_doubles import (
    AMBIENT_TEMP_C,
    INTERFACE_A,
    ROTOR_TEMP_C,
    FakeNodeBus,
    MisaddressedBus,
    arm_channel,
    feedback_payload,
    motors_for,
    target,
)

# The three command codes this tool must never emit (`03` §2.5). Enable is the one that energizes
# a brakeless arm; set-zero writes the flash, whose endurance is 10,000 cycles (`03` NFR-MOT-003);
# write-param changes a motor's stored configuration.
ENABLE_COMMAND_CODE = 0xFC
SET_ZERO_COMMAND_CODE = 0xFE
WRITE_PARAM_COMMAND_CODE = 0x55

# The disable frame as the vendor's own setup documentation writes it (`03` §2.5,
# `cansend can0 001#FFFFFFFFFFFFFFFD`). Spelled here as a literal so this test disagrees with the
# builder if the builder ever changes.
DISABLE_PAYLOAD = bytes.fromhex("FFFFFFFFFFFFFFFD")

# Position quantizes to 12.5 rad over 16 bits; anything inside one LSB is the encoder, not a bug.
POSITION_TOLERANCE_RAD = 1e-3
VELOCITY_TOLERANCE_RAD_S = 2e-2
TORQUE_TOLERANCE_NM = 3e-2

A_SHOULDER_ANGLE = Rad(0.6)
A_WRIST_ANGLE = Rad(-1.2)


def _module_integers() -> list[int]:
    """Every integer literal in the tool's source.

    An absence is only honestly checked statically: a runtime test shows the paths it happened to
    take, and the path that sends the wrong byte is by definition one nobody meant to take.
    """
    tree = ast.parse(Path(watch.__file__).read_text(encoding="utf-8"))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    ]


def test_the_only_command_this_tool_builds_is_disable() -> None:
    """`FF FF FF FF FF FF FF FD` — the vendor's disable frame, byte for byte."""
    assert watch.command_frame(watch.DISABLE_COMMAND_CODE) == DISABLE_PAYLOAD


@pytest.mark.parametrize(
    "code", [ENABLE_COMMAND_CODE, SET_ZERO_COMMAND_CODE, WRITE_PARAM_COMMAND_CODE]
)
def test_no_other_command_code_exists_anywhere_in_the_tool(code: int) -> None:
    """Enable, set-zero and write-param are not reachable, because they are not written down.

    0xFC is the one that matters most: it is what every other reader in this repo sends on
    connect, and it is why those tools make the operator hold the arm first.
    """
    assert code not in _module_integers()


def test_every_frame_a_round_transmits_is_the_disable_frame() -> None:
    """Not just the builder — what actually leaves during a round."""
    arm = target("left", INTERFACE_A, ARM_JOINT_SEND_IDS)
    bus = FakeNodeBus(motors_for(ARM_JOINT_SEND_IDS))

    watch.poll_round([arm_channel(arm, bus)], at_seconds=0.0)

    assert bus.sent, "a round transmitted nothing at all"
    assert {bytes(message.data) for message in bus.sent} == {DISABLE_PAYLOAD}


def test_a_poll_drains_before_it_sends() -> None:
    """A reply that arrived after its own poll timed out must not answer the next one.

    Left in the queue, a node that is consistently one round late reads as a node that is healthy,
    which is the failure this watch exists to catch.
    """
    arm = target("left", INTERFACE_A, (ARM_JOINT_SEND_IDS[0],))
    bus = FakeNodeBus(motors_for((ARM_JOINT_SEND_IDS[0],)))

    watch.poll_round([arm_channel(arm, bus)], at_seconds=0.0)

    assert bus.recv_timeouts[0] == watch.NO_WAIT_S
    assert bus.sent, "the drain consumed the send"


@pytest.mark.parametrize(
    ("send_id", "expected"),
    [(0x01, 0x11), (0x07, 0x17), (GRIPPER_SEND_ID, 0x18)],
)
def test_a_motor_answers_on_its_send_id_plus_the_arm_offset(send_id: int, expected: int) -> None:
    """`03` §2.1: send `0x01–0x08`, recv `0x11–0x18`."""
    assert watch.feedback_id(send_id) == expected


def test_a_frame_carrying_another_motors_id_is_not_that_motors_answer() -> None:
    """Several motors' replies are in flight at once; only the matching id counts as an answer.

    Counting whatever arrived would score a dead node off its neighbour's traffic — the one
    failure mode that makes the whole watch report the opposite of the truth.
    """
    polled = ARM_JOINT_SEND_IDS[0]
    bus = MisaddressedBus(motors_for((polled,)), id_shift=1)
    reader = watch.NodeReader(bus, watch.REPLY_TIMEOUT_S)

    assert reader.poll(polled, MotorType.DM8009) is None


def test_a_feedback_frame_round_trips_through_the_vendor_packing() -> None:
    """Decode is the inverse of `double_to_uint` (`03` §2.3), within one quantization step."""
    sent = watch.MotorFeedback(
        state=watch.STATE_DISABLED,
        motor_id=0x02,
        position=A_SHOULDER_ANGLE,
        velocity=0.4,
        torque_nm=-1.5,
        temp_mos_c=AMBIENT_TEMP_C,
        temp_rotor_c=ROTOR_TEMP_C,
    )

    decoded = watch.decode_feedback(feedback_payload(sent, MotorType.DM8009), MotorType.DM8009)

    assert decoded.state == sent.state
    assert decoded.motor_id == sent.motor_id
    assert decoded.position.value == pytest.approx(sent.position.value, abs=POSITION_TOLERANCE_RAD)
    assert decoded.velocity == pytest.approx(sent.velocity, abs=VELOCITY_TOLERANCE_RAD_S)
    assert decoded.torque_nm == pytest.approx(sent.torque_nm, abs=TORQUE_TOLERANCE_NM)
    assert decoded.temp_mos_c == AMBIENT_TEMP_C
    assert decoded.temp_rotor_c == ROTOR_TEMP_C


def test_the_same_bytes_mean_different_speeds_on_different_motors() -> None:
    """The scaling is per motor type (`03` §2.3), which is why the type is a parameter.

    DM8009 encodes velocity over ±45 rad/s and DM4310 over ±30, so a decoder that assumed one
    type would be off by half on the wrist and never raise anything.
    """
    velocity = 12.0
    sent = watch.MotorFeedback(
        state=watch.STATE_DISABLED,
        motor_id=0x01,
        position=A_WRIST_ANGLE,
        velocity=velocity,
        torque_nm=0.0,
        temp_mos_c=AMBIENT_TEMP_C,
        temp_rotor_c=ROTOR_TEMP_C,
    )
    payload = feedback_payload(sent, MotorType.DM8009)

    as_shoulder = watch.decode_feedback(payload, MotorType.DM8009)
    as_wrist = watch.decode_feedback(payload, MotorType.DM4310)

    assert as_shoulder.velocity == pytest.approx(velocity, abs=VELOCITY_TOLERANCE_RAD_S)
    assert as_wrist.velocity != pytest.approx(velocity, abs=VELOCITY_TOLERANCE_RAD_S)


@pytest.mark.parametrize("state", [watch.STATE_DISABLED, watch.STATE_ENABLED])
def test_disabled_and_enabled_are_both_normal(state: int) -> None:
    """The D0 high nibble is a STATE code, not an error code (`03` §2.7).

    Read as an error field, `0x1` — a motor that is simply enabled — reports a fault on every
    healthy arm on the bus.
    """
    sent = watch.MotorFeedback(
        state=state,
        motor_id=0x01,
        position=A_SHOULDER_ANGLE,
        velocity=0.0,
        torque_nm=0.0,
        temp_mos_c=AMBIENT_TEMP_C,
        temp_rotor_c=ROTOR_TEMP_C,
    )

    decoded = watch.decode_feedback(feedback_payload(sent, MotorType.DM8009), MotorType.DM8009)

    assert not decoded.is_fault
    assert decoded.state_name in ("disabled", "enabled")


@pytest.mark.parametrize(
    ("state", "name"),
    [
        (0x8, "over-voltage"),
        (0x9, "under-voltage"),
        (0xA, "over-current"),
        (0xB, "mos-over-temperature"),
        (0xC, "coil-over-temperature"),
        (0xD, "communication-lost"),
        (0xE, "overloaded"),
    ],
)
def test_a_protection_trip_is_a_fault_and_is_named(state: int, name: str) -> None:
    """`03` §2.7's table, every row. A motor in this state is ANSWERING — that is the point."""
    sent = watch.MotorFeedback(
        state=state,
        motor_id=0x03,
        position=A_WRIST_ANGLE,
        velocity=0.0,
        torque_nm=0.0,
        temp_mos_c=AMBIENT_TEMP_C,
        temp_rotor_c=ROTOR_TEMP_C,
    )

    decoded = watch.decode_feedback(feedback_payload(sent, MotorType.DM4340), MotorType.DM4340)

    assert decoded.is_fault
    assert decoded.state_name == name


def test_a_short_frame_is_refused_rather_than_decoded() -> None:
    """A truncated frame decoded anyway would report an angle assembled from missing bytes."""
    with pytest.raises(watch.FeedbackFrameError):
        watch.decode_feedback(bytes(watch.FEEDBACK_FRAME_LENGTH - 1), MotorType.DM4310)
