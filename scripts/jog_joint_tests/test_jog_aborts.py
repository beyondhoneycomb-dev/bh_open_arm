"""Every way a move stops, and what the motor is left in when it does.

`abort_reason` is judged in isolation per cause, because a check that only ever ran against one
cause is a check that silently lost the other four. One end-to-end case then proves the loop
actually reads the verdict: it stops sending, and it disables.
"""

from __future__ import annotations

from scripts.can_node_watch import (
    DISABLE_COMMAND_CODE,
    LOWEST_FAULT_STATE,
    STATE_DISABLED,
    STATE_ENABLED,
    MotorFeedback,
)
from scripts.jog_joint import AbortLimits, abort_reason
from scripts.jog_joint_tests.jog_doubles import (
    AMBIENT_TEMP_C,
    RESTING_ANGLE,
    ROTOR_TEMP_C,
    WRIST_SEND_ID,
    FakeJogMotor,
    Reply,
    run_jog,
)

MAX_TORQUE_NM = 3.5
MAX_TEMP_C = 80.0
LIMITS = AbortLimits(max_torque_nm=MAX_TORQUE_NM, max_temp_c=MAX_TEMP_C)

# A torque and a temperature that are unambiguously over their ceiling, so a test failure means a
# missing check rather than a rounding argument.
OVER_TORQUE_NM = MAX_TORQUE_NM + 1.0
OVER_TEMP_C = int(MAX_TEMP_C) + 10

# Answers the motor gives before the fault appears: the resting read, the enable, the first poll,
# then two frames of the first leg. Long enough that the abort lands mid-ramp rather than at the
# first stiff frame, which is where a loop that only checks its first answer would still pass.
CLEAN_ANSWERS_BEFORE_FAULT = 5


def _feedback(state: int, torque_nm: float, temp_mos_c: int, temp_rotor_c: int) -> MotorFeedback:
    """One answer from a motor that is otherwise healthy."""
    return MotorFeedback(
        state=state,
        motor_id=WRIST_SEND_ID,
        position=RESTING_ANGLE,
        velocity=0.0,
        torque_nm=torque_nm,
        temp_mos_c=temp_mos_c,
        temp_rotor_c=temp_rotor_c,
    )


def _healthy() -> MotorFeedback:
    """An answer nothing is wrong with."""
    return _feedback(STATE_ENABLED, 0.0, AMBIENT_TEMP_C, ROTOR_TEMP_C)


def test_a_healthy_answer_does_not_stop_the_move() -> None:
    """A check that fires on a clean answer is worse than no check: it disables a loaded joint."""
    assert abort_reason(_healthy(), LIMITS) is None


def test_silence_stops_the_move() -> None:
    """An energized motor that stopped answering is a motor nothing is judging."""
    reason = abort_reason(None, LIMITS)

    assert reason is not None
    assert "피드백" in reason


def test_a_fault_nibble_stops_the_move() -> None:
    """The motor is answering and naming its own protection trip; that is a stop, not a reading."""
    reason = abort_reason(_feedback(LOWEST_FAULT_STATE, 0.0, AMBIENT_TEMP_C, ROTOR_TEMP_C), LIMITS)

    assert reason is not None
    assert "보호" in reason


def test_a_lost_enable_stops_the_move() -> None:
    """A motor that dropped its own enable is no longer holding anything, and must not be ramped."""
    reason = abort_reason(_feedback(STATE_DISABLED, 0.0, AMBIENT_TEMP_C, ROTOR_TEMP_C), LIMITS)

    assert reason is not None
    assert "enable" in reason


def test_torque_over_the_ceiling_stops_the_move() -> None:
    """The joint met something. The sign does not matter, so the magnitude is what is judged."""
    over = abort_reason(
        _feedback(STATE_ENABLED, OVER_TORQUE_NM, AMBIENT_TEMP_C, ROTOR_TEMP_C), LIMITS
    )
    under = abort_reason(
        _feedback(STATE_ENABLED, -OVER_TORQUE_NM, AMBIENT_TEMP_C, ROTOR_TEMP_C), LIMITS
    )

    assert over is not None
    assert under is not None


def test_either_temperature_channel_stops_the_move() -> None:
    """Driver and coil are separate sensors; judging only one leaves the other unwatched."""
    drive = abort_reason(_feedback(STATE_ENABLED, 0.0, OVER_TEMP_C, ROTOR_TEMP_C), LIMITS)
    coil = abort_reason(_feedback(STATE_ENABLED, 0.0, AMBIENT_TEMP_C, OVER_TEMP_C), LIMITS)

    assert drive is not None
    assert coil is not None


def test_a_torque_spike_mid_ramp_stops_the_frames_and_disables() -> None:
    """The end-to-end shape: the loop reads the verdict, stops commanding, and disables.

    Counting the frames is the part that matters. A loop that reported the abort and kept ramping
    would pass an assertion on the returned reason alone.
    """
    script = [Reply()] * CLEAN_ANSWERS_BEFORE_FAULT + [Reply(torque_nm=OVER_TORQUE_NM)]
    motor = FakeJogMotor(WRIST_SEND_ID, RESTING_ANGLE, script)

    reason = run_jog(motor, returns=True)

    assert reason is not None
    assert "토크" in reason
    assert len(motor.mit_commands()) == CLEAN_ANSWERS_BEFORE_FAULT - 1
    assert motor.command_codes()[-1] == DISABLE_COMMAND_CODE
    assert motor.state == STATE_DISABLED


def test_silence_mid_ramp_stops_the_frames_and_disables() -> None:
    """A node that drops off while energized: the run ends, last frame still a disable."""
    script = [Reply()] * CLEAN_ANSWERS_BEFORE_FAULT + [Reply(answers=False)]
    motor = FakeJogMotor(WRIST_SEND_ID, RESTING_ANGLE, script)

    reason = run_jog(motor, returns=True)

    assert reason is not None
    assert motor.command_codes()[-1] == DISABLE_COMMAND_CODE


def test_an_over_temperature_mid_ramp_stops_the_run() -> None:
    """Temperature is the slow one, and the only reason it is judged per frame is that it can be."""
    script = [Reply()] * CLEAN_ANSWERS_BEFORE_FAULT + [Reply(temp_rotor_c=OVER_TEMP_C)]
    motor = FakeJogMotor(WRIST_SEND_ID, RESTING_ANGLE, script)

    reason = run_jog(motor, returns=True)

    assert reason is not None
    assert "온도" in reason


def test_the_returned_reason_names_the_measured_value() -> None:
    """A reason that only names the rule leaves the operator without the reading that broke it."""
    reason = abort_reason(
        _feedback(STATE_ENABLED, OVER_TORQUE_NM, AMBIENT_TEMP_C, ROTOR_TEMP_C), LIMITS
    )

    assert reason is not None
    assert f"{OVER_TORQUE_NM:+.2f}" in reason
    assert f"{MAX_TORQUE_NM:.2f}" in reason
