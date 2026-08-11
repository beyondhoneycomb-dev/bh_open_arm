"""Property 5 — the far end of the move is inside the joint's soft envelope, and nothing is
energized when it is not.

The load-bearing assertion in this file is not that a refusal happens; it is that `0xFC` never
reached the motor when it did. A limit check that refuses *after* enabling has not prevented
anything — the arm is already holding a target it was refused — so the wire test reads the
command bytes rather than the return value.

The envelope's provenance is checked too, and for a reason `03` §2.9 states outright: four of the
five limit sets are declared in `F_URDF` and this tool commands in `F_motor`. A test that only
asserted "some bound was applied" would pass over a set from the wrong frame, which on `J2` is a
99-degree error and on the others is silent.
"""

from __future__ import annotations

import pytest

from contracts.units import Rad
from scripts.jog_joint import (
    ENABLE_COMMAND_CODE,
    SOFT_LIMIT_SET_NAME,
    JogPlan,
    JogRefusedError,
    JointEnvelope,
    envelope_refusal,
    jog,
    resolve_envelope,
)
from scripts.jog_joint_tests.jog_doubles import (
    FAST_PERIOD_S,
    LEFT_SIDE,
    NO_HOLD_FRAMES,
    SMALL_DELTA,
    SMALL_FRAMES,
    TEST_LIMITS,
    WRIST_SEND_ID,
    FakeJogBus,
    FakeJogMotor,
    wrist_gains,
    wrist_target,
)
from sim.ik.limits import arm_soft_limits

# The wrist's LeRobot bound is ±80°; this rests 77.3° out, so `SMALL_DELTA` (5.7°) carries the
# target past it. A joint parked near its bound is what makes this reachable at the bench without
# an oversized delta — `MAX_DELTA_DEG` already refuses those, and the two guards are independent.
NEAR_UPPER_BOUND = Rad(1.35)

# Far enough outside the same bound that a move of `SMALL_DELTA` in either direction stays outside,
# which is what separates "moving back" from "moving further out".
BEYOND_UPPER_BOUND = Rad(1.55)

# A joint id whose LeRobot bound is not symmetric, so a left/right mix-up is visible in the values.
# `J2` is right `(-9, +90)` and left `(-90, +9)`; every other arm joint is symmetric and would let
# a swapped side pass unnoticed (`03` §2.9: "J3-J7 are symmetric, which is what makes the missing
# mirroring look like there is none").
ASYMMETRIC_SEND_ID = 0x02

# An envelope stated directly, for the cases that are about the rule rather than about the source.
BAND = JointEnvelope(lower=Rad(-1.0), upper=Rad(1.0), source="test band")


def _plan_at(delta: Rad) -> JogPlan:
    """A wrist move of `delta`, built past `MAX_DELTA_DEG` because that guard is a separate one."""
    return JogPlan(
        target=wrist_target(),
        delta=delta,
        gains=wrist_gains(),
        frames=SMALL_FRAMES,
        period_s=FAST_PERIOD_S,
        hold_frames=NO_HOLD_FRAMES,
        returns=True,
        limits=TEST_LIMITS,
    )


def test_a_target_inside_the_band_is_not_refused() -> None:
    """The rule is not vacuous: a move that stays inside returns no refusal."""
    assert envelope_refusal(BAND, Rad(0.0), Rad(0.5)) is None


def test_a_target_outside_the_band_is_refused_and_the_reason_names_the_band() -> None:
    """A target past the upper bound is refused, and the refusal says which envelope refused it.

    The message is the operator's only account of why the arm did not move, so it carries the
    band's name and the fact that nothing was energized — a bare "refused" would send someone
    looking for a fault on a motor that was never enabled.
    """
    refusal = envelope_refusal(BAND, Rad(0.9), Rad(1.1))

    assert refusal is not None
    assert BAND.source in refusal
    assert "통전하지 않았다" in refusal


def test_a_joint_already_outside_may_move_back_in() -> None:
    """A joint parked past a bound is jogged back — refusing this leaves it stuck out there."""
    assert envelope_refusal(BAND, Rad(1.2), Rad(1.1)) is None


def test_a_joint_already_outside_may_not_move_further_out() -> None:
    """The same joint moving the other way is refused: the violation must not grow."""
    assert envelope_refusal(BAND, Rad(1.1), Rad(1.2)) is not None


def test_a_move_that_lands_back_inside_from_outside_is_allowed() -> None:
    """Coming all the way back inside is the zero-violation case, not the reducing one."""
    assert envelope_refusal(BAND, Rad(1.2), Rad(0.0)) is None


def test_the_violation_is_zero_inside_and_the_distance_outside() -> None:
    """`violation` is the distance past the nearer bound, and zero anywhere between them."""
    assert BAND.violation(Rad(0.0)) == 0.0
    assert BAND.violation(Rad(1.0)) == 0.0
    assert BAND.violation(Rad(1.25)) == pytest.approx(0.25)
    assert BAND.violation(Rad(-1.25)) == pytest.approx(0.25)


def test_the_envelope_is_the_lerobot_set_for_that_side_and_joint() -> None:
    """The bounds are LeRobot's own, not a second copy — compared against the upstream source."""
    resolved = resolve_envelope(LEFT_SIDE, WRIST_SEND_ID)
    upstream = arm_soft_limits(LEFT_SIDE)[WRIST_SEND_ID - 1]

    assert resolved.lower == upstream.lower_rad
    assert resolved.upper == upstream.upper_rad
    assert resolved.source == SOFT_LIMIT_SET_NAME


def test_the_two_arms_get_their_own_bounds_on_an_asymmetric_joint() -> None:
    """`J2` is `(-9, +90)` right and `(-90, +9)` left; one shared vector would fail this."""
    left = resolve_envelope("left", ASYMMETRIC_SEND_ID)
    right = resolve_envelope("right", ASYMMETRIC_SEND_ID)

    assert left.lower.value == pytest.approx(-right.upper.value)
    assert left.upper.value == pytest.approx(-right.lower.value)
    assert left.upper.value < right.upper.value


def test_an_out_of_band_move_never_sends_the_enable_frame() -> None:
    """The refusal lands before `0xFC`, so the motor is never energized (property 5)."""
    motor = FakeJogMotor(WRIST_SEND_ID, NEAR_UPPER_BOUND, None)

    with pytest.raises(JogRefusedError):
        jog(_plan_at(SMALL_DELTA), FakeJogBus(motor, None))

    assert ENABLE_COMMAND_CODE not in motor.command_codes()
    assert motor.mit_commands() == []


def test_the_refused_run_still_closes_with_a_disable() -> None:
    """The `finally` covers the refusal too: the last frame the motor sees is a disable."""
    motor = FakeJogMotor(WRIST_SEND_ID, NEAR_UPPER_BOUND, None)

    with pytest.raises(JogRefusedError):
        jog(_plan_at(SMALL_DELTA), FakeJogBus(motor, None))

    assert motor.command_codes()[-1] != ENABLE_COMMAND_CODE


def test_a_joint_parked_outside_is_jogged_back_on_the_wire() -> None:
    """Moving inward from outside runs to completion, so the rule is not a blanket refusal."""
    motor = FakeJogMotor(WRIST_SEND_ID, BEYOND_UPPER_BOUND, None)

    assert jog(_plan_at(Rad(-SMALL_DELTA.value)), FakeJogBus(motor, None)) is None
    assert ENABLE_COMMAND_CODE in motor.command_codes()
