"""The ramp: it spans both ends, it never jumps, and it departs from where the motor already is.

These are pure-value tests over `ramp` and `plan_legs`, with no bus at all. That the planning is
separable from the wire is what makes property 1 assertable without energizing anything.
"""

from __future__ import annotations

import pytest

from contracts.units import Rad
from scripts.jog_joint import MIN_RAMP_FRAMES, plan_legs, ramp

RESTING = Rad(0.37)
DELTA = Rad(0.5)
FRAMES = 40

# Two ramp endpoints that differ in sign, so a monotonicity check cannot pass by reading the
# magnitude of a one-directional ramp.
DESCENDING_START = Rad(1.0)
DESCENDING_END = Rad(-1.0)


def test_a_ramp_starts_exactly_where_it_was_told_to_start() -> None:
    """Property 1 lives here: the first commanded position is the present one, not near it.

    "Near" is not enough. The jump on enable is proportional to the position error, so a first
    target that is close but not equal is a smaller jump rather than no jump.
    """
    targets = ramp(RESTING, RESTING + DELTA, FRAMES)

    assert targets[0] == RESTING


def test_a_ramp_ends_exactly_on_its_target() -> None:
    """An accumulated-increment ramp drifts off its endpoint; this one is computed, not summed."""
    targets = ramp(RESTING, RESTING + DELTA, FRAMES)

    assert targets[-1] == RESTING + DELTA


def test_a_ramp_emits_the_frames_it_was_asked_for() -> None:
    """The frame count is what turns ramp seconds into a number of frames on the wire."""
    assert len(ramp(RESTING, RESTING + DELTA, FRAMES)) == FRAMES


def test_a_ramp_only_ever_moves_one_way() -> None:
    """Property 2: no step reverses and no step repeats, in either direction of travel."""
    rising = ramp(RESTING, RESTING + DELTA, FRAMES)
    falling = ramp(DESCENDING_START, DESCENDING_END, FRAMES)

    assert all(later > earlier for earlier, later in zip(rising, rising[1:], strict=False))
    assert all(later < earlier for earlier, later in zip(falling, falling[1:], strict=False))


def test_a_ramp_takes_even_steps() -> None:
    """An uneven ramp is a jump wearing a ramp's shape."""
    targets = ramp(RESTING, RESTING + DELTA, FRAMES)
    steps = [
        later.value - earlier.value for earlier, later in zip(targets, targets[1:], strict=False)
    ]

    assert max(steps) == pytest.approx(min(steps))
    assert max(steps) == pytest.approx(DELTA.value / (FRAMES - 1))


def test_a_one_frame_ramp_is_refused() -> None:
    """One frame is the jump, exactly: a single target with no departure point."""
    with pytest.raises(ValueError, match=str(MIN_RAMP_FRAMES)):
        ramp(RESTING, RESTING + DELTA, MIN_RAMP_FRAMES - 1)


def test_a_zero_delta_ramp_holds_the_present_position() -> None:
    """A zero move is a legitimate request — enable, hold where you are, disable — not an error."""
    targets = ramp(RESTING, RESTING, FRAMES)

    assert all(target == RESTING for target in targets)


def test_the_first_leg_departs_from_the_resting_position() -> None:
    """The resting position is read before anything is energized, and the plan starts there."""
    legs = plan_legs(RESTING, DELTA, FRAMES, returns=True)

    assert legs[0][0] == RESTING


def test_the_return_leg_lands_back_on_the_resting_position() -> None:
    """Coming back is the whole second half of what this tool promises."""
    legs = plan_legs(RESTING, DELTA, FRAMES, returns=True)

    assert len(legs) == 2
    assert legs[1][0] == RESTING + DELTA
    assert legs[1][-1] == RESTING


def test_no_return_plans_one_leg_and_leaves_the_joint_where_it_arrived() -> None:
    """`--no-return` drops the second leg; it does not shorten or truncate the first."""
    legs = plan_legs(RESTING, DELTA, FRAMES, returns=False)

    assert len(legs) == 1
    assert legs[0][-1] == RESTING + DELTA
