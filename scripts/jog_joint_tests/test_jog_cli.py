"""The command line: it renders, and what it parses becomes the move that runs.

Nothing here opens a channel. `build_plan` is the whole crossing from what the operator typed to
what goes on the wire — degrees in, radians out, one abort torque derived per joint — so a wrong
default here is a wrong move with every other property still passing.
"""

from __future__ import annotations

import math

import pytest

from backend.actuation.gains import COMPLIANT, STIFF, resolve_gain_profile
from backend.can.rid.layout import expected_type
from backend.excitation.constants import DEFAULT_MAX_MOTOR_TEMP_C
from backend.safety_bringup.constants import URDF_EFFORT_LIMIT_NM
from contracts.units import Rad
from scripts.jog_joint import (
    ABORT_TORQUE_FRACTION_OF_EFFORT,
    DEFAULT_PROFILE_NAME,
    MIN_RAMP_FRAMES,
    OVERRIDE_KD_FLAG,
    OVERRIDE_KP_FLAG,
    JogPlan,
    JogTarget,
    build_parser,
    build_plan,
    resolve_envelope,
)
from scripts.jog_joint_tests.jog_doubles import (
    LEFT_INTERFACE,
    LEFT_SIDE,
    WRIST_SEND_ID,
    wrist_target,
)

BASE_ARGV = ["--arm", "left", "--id", "0x07", "--delta", "5"]

# The elbow, and the two `compliant` entries that make the per-joint lookup visible: J4 kp 60
# against J7 kp 10 (`03` §2.8). On this rig kp=10 moved the elbow 0.02° of a commanded 5° while
# kp=60 moved it 3.4°, so this is the difference a scalar default gets wrong.
ELBOW_SEND_ID = 0x04
ELBOW_ARGV = ["--arm", "left", "--id", "0x04", "--delta", "5"]
COMPLIANT_ELBOW_KP = 60.0
COMPLIANT_ELBOW_KD = 2.0
COMPLIANT_WRIST_KP = 10.0

# The stiffness the operator reached for by hand when the elbow would not move.
PROBE_KP = "60"
PROBE_KD = "1.5"

# A name that is not in the `03` §2.8 registry.
UNREGISTERED_PROFILE = "medium"

# `URDF_EFFORT_LIMIT_NM` is indexed from J1, which is CAN send id 0x01.
FIRST_ARM_SEND_ID = 0x01

RIGHT_ANGLE_DEG = "90"
SLOW_SECONDS = "4"
SLOW_HZ = "10"

# A ramp shorter than one frame period, which `round(hz * seconds)` alone answers with zero.
SUB_FRAME_SECONDS = "0.001"

HOLD_SECONDS = "2"


def _plan_from(argv: list[str]) -> JogPlan:
    """Parse an argument list and build the plan it names, against the wrist joint."""
    return build_plan(wrist_target(), build_parser().parse_args(argv))


def _elbow_target() -> JogTarget:
    """The left arm's elbow, as `resolve_target` would have produced it."""
    return JogTarget(
        side=LEFT_SIDE,
        interface=LEFT_INTERFACE,
        send_id=ELBOW_SEND_ID,
        motor_type=expected_type(ELBOW_SEND_ID),
        effort_limit_nm=URDF_EFFORT_LIMIT_NM[ELBOW_SEND_ID - FIRST_ARM_SEND_ID],
        envelope=resolve_envelope(LEFT_SIDE, ELBOW_SEND_ID),
    )


def _elbow_plan_from(argv: list[str]) -> JogPlan:
    """Parse an argument list and build the plan it names, against the elbow joint."""
    return build_plan(_elbow_target(), build_parser().parse_args(argv))


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


def test_the_gains_come_from_the_named_profile_at_this_joint() -> None:
    """The same command line resolves to different gains on different joints, which is the point.

    `compliant` is kp 60 at the elbow and kp 10 at the wrist. A scalar default is wrong at one of
    those two ends whichever value it takes, and the bench proved which way: kp=10 moved the elbow
    0.02° of a commanded 5°.
    """
    assert _elbow_plan_from(ELBOW_ARGV).gains.kp == COMPLIANT_ELBOW_KP
    assert _elbow_plan_from(ELBOW_ARGV).gains.kd == COMPLIANT_ELBOW_KD
    assert _plan_from(BASE_ARGV).gains.kp == COMPLIANT_WRIST_KP


def test_the_default_profile_is_the_registered_compliant_set() -> None:
    """Unloaded joint, hand-sized deltas, a hand near the arm — the softest set the spec has."""
    assert DEFAULT_PROFILE_NAME == COMPLIANT
    assert _plan_from(BASE_ARGV).gains.profile_name == COMPLIANT


def test_a_named_profile_replaces_the_default_whole() -> None:
    """Naming a profile changes every joint's pair at once, which a per-flag gain could not do."""
    plan = _elbow_plan_from([*ELBOW_ARGV, "--profile", STIFF])
    registered = resolve_gain_profile(STIFF).for_send_id(ELBOW_SEND_ID)

    assert plan.gains.profile_name == STIFF
    assert (plan.gains.kp, plan.gains.kd) == (registered.kp, registered.kd)


def test_an_unregistered_profile_name_is_a_usage_error() -> None:
    """The registry refuses rather than defaulting, and the refusal reaches the command line.

    A silently substituted profile would run gains nobody chose while reporting a name nobody
    typed (`13` FR-GUI-068).
    """
    with pytest.raises(SystemExit):
        build_parser().parse_args([*BASE_ARGV, "--profile", UNREGISTERED_PROFILE])


def test_an_override_replaces_one_half_and_leaves_the_other_registered() -> None:
    """Probing one joint by hand is legitimate; losing track of which half was probed is not."""
    plan = _elbow_plan_from([*ELBOW_ARGV, OVERRIDE_KP_FLAG, PROBE_KP])

    assert plan.gains.kp == float(PROBE_KP)
    assert plan.gains.kd == COMPLIANT_ELBOW_KD
    assert plan.gains.overridden == (OVERRIDE_KP_FLAG,)


def test_both_halves_can_be_overridden_together() -> None:
    """A probe that names both is still a probe, and both flags are reported."""
    plan = _elbow_plan_from([*ELBOW_ARGV, OVERRIDE_KP_FLAG, PROBE_KP, OVERRIDE_KD_FLAG, PROBE_KD])

    assert (plan.gains.kp, plan.gains.kd) == (float(PROBE_KP), float(PROBE_KD))
    assert plan.gains.overridden == (OVERRIDE_KP_FLAG, OVERRIDE_KD_FLAG)


def test_an_overridden_run_cannot_be_read_back_as_a_profile_run() -> None:
    """The label is what the operator reads and what a log carries, so it names the override.

    Reporting the profile name alone would make a hand-probed run look repeatable from that name,
    and it is not: nothing in the registry carries this stiffness.
    """
    plan = _elbow_plan_from([*ELBOW_ARGV, OVERRIDE_KP_FLAG, PROBE_KP])

    assert OVERRIDE_KP_FLAG in plan.gains.label
    assert COMPLIANT in plan.gains.label


def test_a_run_on_a_registered_profile_says_only_that() -> None:
    """No override, no override marker — otherwise the marker means nothing."""
    assert _plan_from(BASE_ARGV).gains.overridden == ()
    assert OVERRIDE_KP_FLAG not in _plan_from(BASE_ARGV).gains.label
