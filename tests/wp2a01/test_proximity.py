"""The near-limit warning and the direction refusal `04` FR-MAN-013 asks for.

Both verdicts belong to the backend because the screen must not compute them: a browser that
decided "at limit" from the position would be a second clamp with its own rounding, and the two
would disagree on exactly the samples where it matters. These tests pin the boundary cases,
which is where a recomputation would drift.
"""

from __future__ import annotations

import pytest

from backend.jog.config import NEAR_LIMIT_MARGIN_DEG
from backend.jog.proximity import BlockedDirection, evaluate_proximity
from contracts.units import Deg, deg_to_rad
from sim.ik.limits import JointLimit, soft_limits

MARGIN = 5.0
BOUND_DEG = 75.0

# A symmetric bound, so a test that transposed lower and upper would still be wrong somewhere.
# The real sets are asymmetric — the last test says so — but symmetry here is what makes a
# transposition show up as a sign rather than as a different magnitude.
LIMIT = JointLimit(
    mjcf_joint="openarm_left_joint1",
    lower_deg=Deg(-BOUND_DEG),
    upper_deg=Deg(BOUND_DEG),
    lower_rad=deg_to_rad(Deg(-BOUND_DEG)),
    upper_rad=deg_to_rad(Deg(BOUND_DEG)),
)


def test_mid_range_is_neither_near_nor_blocked() -> None:
    verdict = evaluate_proximity(Deg(0.0), LIMIT, MARGIN)

    assert verdict.near_limit is False
    assert verdict.blocked_direction is BlockedDirection.NONE


@pytest.mark.parametrize("position", [70.1, 74.0, -70.1, -74.0])
def test_inside_the_margin_is_near_but_still_free_to_move(position: float) -> None:
    """The whole point of the warning: it arrives while there is still room to stop."""
    verdict = evaluate_proximity(Deg(position), LIMIT, MARGIN)

    assert verdict.near_limit is True
    assert verdict.blocked_direction is BlockedDirection.NONE


def test_exactly_on_the_margin_is_near() -> None:
    """Boundary inclusive. A joint five degrees out is what the five-degree warning is about."""
    assert evaluate_proximity(Deg(70.0), LIMIT, MARGIN).near_limit is True


def test_exactly_on_the_bound_blocks_that_direction() -> None:
    verdict = evaluate_proximity(Deg(75.0), LIMIT, MARGIN)

    assert verdict.blocked_direction is BlockedDirection.POSITIVE
    assert verdict.near_limit is True


def test_the_two_bounds_block_opposite_directions() -> None:
    """A transposed comparison would refuse the way back and permit the way out."""
    assert evaluate_proximity(Deg(75.0), LIMIT, MARGIN).blocked_direction is (
        BlockedDirection.POSITIVE
    )
    assert evaluate_proximity(Deg(-75.0), LIMIT, MARGIN).blocked_direction is (
        BlockedDirection.NEGATIVE
    )


@pytest.mark.parametrize(
    ("position", "blocked"),
    [(120.0, BlockedDirection.POSITIVE), (-120.0, BlockedDirection.NEGATIVE)],
)
def test_a_joint_parked_outside_the_set_keeps_the_way_back(
    position: float, blocked: BlockedDirection
) -> None:
    """Reachable in practice: the soft limits are LeRobot's, the hard stops are the mechanism's.

    Blocking both directions here would need a bus session and a hex key to undo, so only the
    direction that takes the joint further out is refused.
    """
    assert evaluate_proximity(Deg(position), LIMIT, MARGIN).blocked_direction is blocked


def test_the_margin_the_frame_uses_is_the_spec_default() -> None:
    """`04` FR-MAN-013 states five degrees of remaining travel, and the frame is built with it."""
    assert NEAR_LIMIT_MARGIN_DEG == 5.0


def test_the_real_limits_are_asymmetric_so_the_two_bounds_cannot_be_one_number() -> None:
    """Left and right differ and so do the joints; a single symmetric bound would be a fiction."""
    j2 = soft_limits("left")[1]

    assert j2.lower_deg.value != -j2.upper_deg.value
