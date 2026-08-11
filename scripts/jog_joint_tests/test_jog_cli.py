"""The command line: it renders, and what it parses becomes the move that runs.

Nothing here opens a channel. `build_plan` is the whole crossing from what the operator typed to
what goes on the wire — degrees in, radians out, one abort torque derived per joint — so a wrong
default here is a wrong move with every other property still passing.
"""

from __future__ import annotations

import math

import pytest

from backend.excitation.constants import DEFAULT_MAX_MOTOR_TEMP_C
from contracts.units import Rad
from scripts.jog_joint import (
    ABORT_TORQUE_FRACTION_OF_EFFORT,
    MIN_RAMP_FRAMES,
    JogPlan,
    build_parser,
    build_plan,
)
from scripts.jog_joint_tests.jog_doubles import WRIST_SEND_ID, wrist_target

BASE_ARGV = ["--arm", "left", "--id", "0x07", "--delta", "5"]

RIGHT_ANGLE_DEG = "90"
SLOW_SECONDS = "4"
SLOW_HZ = "10"

# A ramp shorter than one frame period, which `round(hz * seconds)` alone answers with zero.
SUB_FRAME_SECONDS = "0.001"

HOLD_SECONDS = "2"


def _plan_from(argv: list[str]) -> JogPlan:
    """Parse an argument list and build the plan it names, against the wrist joint."""
    return build_plan(wrist_target(), build_parser().parse_args(argv))


def test_the_help_text_renders() -> None:
    """argparse expands `%` in help strings, so a literal one raises only when help is asked for.

    Nothing else in this file would catch it: every other test builds the parser and never
    formats it, and the operator finds it on their first `--help`.
    """
    assert build_parser().format_help()


def test_the_id_accepts_the_hex_the_operator_reads_off_the_arm() -> None:
    """CAN ids are written in hex everywhere else here and in the vendor's own docs."""
    assert build_parser().parse_args(BASE_ARGV).send_id == WRIST_SEND_ID


def test_degrees_become_radians_exactly_once() -> None:
    """CTR-UNIT@v1: the CLI is degrees, the frame is radians, and the crossing happens here.

    A second conversion is the classic factor-of-57.3 bug, and it executes without an error
    anywhere.
    """
    plan = _plan_from(["--arm", "left", "--id", "0x07", "--delta", RIGHT_ANGLE_DEG])

    assert plan.delta == Rad(math.radians(float(RIGHT_ANGLE_DEG)))


def test_the_frame_count_follows_the_ramp_seconds_and_rate() -> None:
    """Frames are what the operator's seconds and Hz actually become on the wire."""
    plan = _plan_from([*BASE_ARGV, "--seconds", SLOW_SECONDS, "--hz", SLOW_HZ])

    assert plan.frames == int(SLOW_SECONDS) * int(SLOW_HZ)
    assert plan.period_s == pytest.approx(1.0 / int(SLOW_HZ))


def test_a_ramp_too_short_to_have_frames_still_has_both_ends() -> None:
    """`round(hz * seconds)` answers zero or one here, and either would be the jump, not a ramp."""
    plan = _plan_from([*BASE_ARGV, "--seconds", SUB_FRAME_SECONDS])

    assert plan.frames == MIN_RAMP_FRAMES


def test_the_abort_torque_defaults_to_a_fraction_of_this_joint_s_effort_limit() -> None:
    """Per joint, because one flat number is either useless at the wrist or a false abort at the
    shoulder — where the gravity hold alone reaches 11.67 N·m."""
    target = wrist_target()

    plan = _plan_from(BASE_ARGV)

    assert plan.limits.max_torque_nm == pytest.approx(
        target.effort_limit_nm * ABORT_TORQUE_FRACTION_OF_EFFORT
    )


def test_a_named_abort_torque_replaces_the_derived_one() -> None:
    """The derivation is a default, not a floor: a jog into something soft wants a lower one."""
    plan = _plan_from([*BASE_ARGV, "--max-torque", "1.0"])

    assert plan.limits.max_torque_nm == pytest.approx(1.0)


def test_the_abort_temperature_is_the_project_s_own_injection_ceiling() -> None:
    """The same ceiling the excitation harness aborts on, not the motor's fault cap."""
    assert _plan_from(BASE_ARGV).limits.max_temp_c == pytest.approx(DEFAULT_MAX_MOTOR_TEMP_C)


def test_the_return_leg_is_on_unless_it_is_turned_off() -> None:
    """Coming back is the default; leaving the joint somewhere else has to be asked for."""
    assert _plan_from(BASE_ARGV).returns
    assert not _plan_from([*BASE_ARGV, "--no-return"]).returns


def test_the_hold_becomes_a_frame_count() -> None:
    """A hold is frames at the far end, so it is judged like every other frame rather than slept."""
    plan = _plan_from([*BASE_ARGV, "--hz", SLOW_HZ, "--hold", HOLD_SECONDS])

    assert plan.hold_frames == int(SLOW_HZ) * int(HOLD_SECONDS)


def test_a_zero_hold_turns_the_hold_off() -> None:
    """Zero is how an operator asks for out-and-straight-back, and it is not an error."""
    assert _plan_from([*BASE_ARGV, "--hold", "0"]).hold_frames == 0


def test_a_rate_of_zero_is_a_usage_error_rather_than_a_traceback() -> None:
    """`1 / hz` and `round(hz * seconds)` both fail on zero, and the operator sees which flag."""
    for argv in ([*BASE_ARGV, "--hz", "0"], [*BASE_ARGV, "--seconds", "0"]):
        with pytest.raises(SystemExit):
            build_parser().parse_args(argv)


def test_a_negative_hold_is_a_usage_error() -> None:
    """A negative duration is a typo, and rounding it to zero would hide the typo."""
    with pytest.raises(SystemExit):
        build_parser().parse_args([*BASE_ARGV, "--hold", "-1"])
