"""What actually goes on the wire: the first target, the enable poll, and the closing disable.

Every assertion here reads the frames the motor received, decoded off `03` §2.3's byte table by
the double. A test that checked the planner instead would pass over an encoder that puts the
position in the wrong bytes, and the property that matters — that the motor is asked for the
place it is already in — is a property of those bytes.
"""

from __future__ import annotations

import pytest

from scripts.can_node_watch import (
    DISABLE_COMMAND_CODE,
    STATE_DISABLED,
    STATE_ENABLED,
    command_frame,
)
from scripts.jog_joint import ENABLE_COMMAND_CODE, MotorLink, jog
from scripts.jog_joint_tests.jog_doubles import (
    POSITION_LSB_RAD,
    RESTING_ANGLE,
    SMALL_DELTA,
    SMALL_FRAMES,
    TORQUE_LSB_NM,
    WRIST_SEND_ID,
    FakeJogBus,
    FakeJogMotor,
    Reply,
    SendFailedError,
    is_command_frame,
    run_jog,
    small_move_plan,
)

# The send index that raises in the disable-on-exception test. Sends run: 0 the torque-free
# resting read, 1 the enable, 2 the first enable poll, 3 onwards the first leg — so this lands
# mid-leg, with the motor energized.
FAILING_SEND_INDEX = 4

# Frames the far end is held for, in the one test that asks for a hold.
HOLD_FRAMES = 3


def test_the_first_commanded_position_is_the_one_the_motor_is_already_in() -> None:
    """Property 1, on the wire. This is the one that throws an arm when it is wrong.

    A motor enabled with a target it is not at drives there immediately, with a force
    proportional to kp. Both the poll frames and the first stiff frame therefore name the resting
    position, and "within one LSB" is as exact as a 16-bit field can be.
    """
    motor = FakeJogMotor(WRIST_SEND_ID, RESTING_ANGLE, None)

    assert run_jog(motor, returns=True) is None

    commands = motor.mit_commands()
    stiff = [command for command in commands if command.kp > 0.0]
    assert commands[0].position.value == pytest.approx(RESTING_ANGLE.value, abs=POSITION_LSB_RAD)
    assert stiff[0].position.value == pytest.approx(RESTING_ANGLE.value, abs=POSITION_LSB_RAD)


def test_the_enable_poll_frames_command_no_force() -> None:
    """Polling is only safe because these frames produce nothing: kp, kd and tau all zero.

    A poll carrying a gain would be a command, and the tool would be commanding a motor whose
    state it has not yet confirmed.
    """
    motor = FakeJogMotor(WRIST_SEND_ID, RESTING_ANGLE, None)

    assert run_jog(motor, returns=True) is None

    probes = [command for command in motor.mit_commands() if command.kp == 0.0]
    assert probes
    assert all(probe.kd == 0.0 for probe in probes)
    assert all(probe.torque_ff_nm == pytest.approx(0.0, abs=TORQUE_LSB_NM) for probe in probes)


def test_the_reply_to_the_enable_frame_still_says_disabled() -> None:
    """Why confirmation is polled: the answer carries the state from before the command.

    A single-shot check reads this reply and concludes the enable failed, every time, on a motor
    that did enable.
    """
    motor = FakeJogMotor(WRIST_SEND_ID, RESTING_ANGLE, None)
    link = MotorLink(FakeJogBus(motor), WRIST_SEND_ID, motor.motor_type)

    reply = link.exchange(command_frame(ENABLE_COMMAND_CODE), 1.0)

    assert reply is not None
    assert reply.state == STATE_DISABLED
    assert motor.state == STATE_ENABLED


def test_the_run_reads_the_resting_position_with_a_torque_free_frame() -> None:
    """The position property 1 departs from is read before anything energizes, by 0xFD."""
    motor = FakeJogMotor(WRIST_SEND_ID, RESTING_ANGLE, None)

    assert run_jog(motor, returns=True) is None

    assert is_command_frame(motor.received[0])
    assert motor.command_codes()[0] == DISABLE_COMMAND_CODE


def test_a_clean_run_ends_disabled() -> None:
    """Property 4 on the ordinary path: the last frame a motor sees is always the disable."""
    motor = FakeJogMotor(WRIST_SEND_ID, RESTING_ANGLE, None)

    assert run_jog(motor, returns=True) is None

    assert motor.command_codes() == [
        DISABLE_COMMAND_CODE,
        ENABLE_COMMAND_CODE,
        DISABLE_COMMAND_CODE,
    ]
    assert motor.state == STATE_DISABLED


def test_an_exception_mid_move_still_disables() -> None:
    """Property 4 on the path nobody plans for.

    A link that goes away mid-leg is not an abort the tool knows how to name, so it propagates —
    but it propagates through the `finally`, and the motor is left disabled rather than energized
    and unattended.
    """
    motor = FakeJogMotor(WRIST_SEND_ID, RESTING_ANGLE, None)
    bus = FakeJogBus(motor, fail_on_send=FAILING_SEND_INDEX)

    with pytest.raises(SendFailedError):
        jog(small_move_plan(returns=True), bus)

    assert motor.command_codes()[-1] == DISABLE_COMMAND_CODE
    assert motor.state == STATE_DISABLED


def test_a_completed_move_returns_to_where_it_started() -> None:
    """Coming back is half of what this tool promises, and the double follows what it is told."""
    motor = FakeJogMotor(WRIST_SEND_ID, RESTING_ANGLE, None)

    assert run_jog(motor, returns=True) is None

    assert motor.position.value == pytest.approx(RESTING_ANGLE.value, abs=POSITION_LSB_RAD)


def test_no_return_leaves_the_joint_where_it_arrived() -> None:
    """`--no-return` is the one way this tool leaves a joint somewhere else."""
    motor = FakeJogMotor(WRIST_SEND_ID, RESTING_ANGLE, None)

    assert run_jog(motor, returns=False) is None

    reached = RESTING_ANGLE + SMALL_DELTA
    assert motor.position.value == pytest.approx(reached.value, abs=POSITION_LSB_RAD)


def test_a_motor_that_never_reports_enabled_stops_the_run_before_any_stiff_frame() -> None:
    """An enable that did not take must not be followed by a frame carrying a gain.

    The motor here answers everything and stays disabled, which is what a node whose enable was
    refused looks like: silence would be a different diagnosis.
    """
    motor = FakeJogMotor(WRIST_SEND_ID, RESTING_ANGLE, [Reply(state=STATE_DISABLED)])

    reason = run_jog(motor, returns=True)

    assert reason is not None
    assert "enable" in reason
    assert all(command.kp == 0.0 for command in motor.mit_commands())
    assert motor.command_codes()[-1] == DISABLE_COMMAND_CODE


def test_the_hold_keeps_commanding_the_far_end() -> None:
    """A held position with no traffic is not a hold.

    The motor's comm-loss timeout drops its enable when frames stop, and until it does, nothing is
    reading the temperature. So the hold is frames, not a sleep.
    """
    motor = FakeJogMotor(WRIST_SEND_ID, RESTING_ANGLE, None)

    assert run_jog(motor, returns=True, hold_frames=HOLD_FRAMES) is None

    stiff = [command for command in motor.mit_commands() if command.kp > 0.0]
    assert len(stiff) == SMALL_FRAMES * 2 + HOLD_FRAMES
    reached = RESTING_ANGLE + SMALL_DELTA
    held = stiff[SMALL_FRAMES : SMALL_FRAMES + HOLD_FRAMES]
    assert all(
        command.position.value == pytest.approx(reached.value, abs=POSITION_LSB_RAD)
        for command in held
    )
