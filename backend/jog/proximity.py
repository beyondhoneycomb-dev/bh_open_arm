"""How close a joint is to its soft limit, and which way it may no longer go.

`04` FR-MAN-013 asks for two things the screen must not decide for itself: a warning
while a joint still has room, and a refusal of the one direction once it has none. The
screen renders both and computes neither — a browser that recomputed "at limit" from the
position would be a second clamp with its own rounding, disagreeing with the gateway's on
exactly the samples that matter.

The verdict is a pure function of one reading and one bound, so every branch — inside the
margin, on the bound, past it — is reachable without a bus. Past it is reachable in
practice too: the soft limits are LeRobot's, the hard stops are the mechanism's, and a
joint parked by hand outside the soft set reads exactly that way on connect.

Degrees, because that is the unit both sides of the comparison already carry:
`ArmState.joint_deg` is what the bus answered and `JointLimit` keeps the LeRobot degrees
beside the radians it converted. Converting either would put a rounding between the value
and the bound it is judged against.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from contracts.units import Deg
from sim.ik.limits import JointLimit


class BlockedDirection(Enum):
    """The jog direction a joint's own position has taken away.

    Named rather than a bare sign so the wire value says what it means: `POSITIVE` is
    "increasing this joint is refused", which is the upper bound, and a reader that had to
    remember the sign convention would eventually invert it.
    """

    NONE = "none"
    POSITIVE = "positive"
    NEGATIVE = "negative"


@dataclass(frozen=True)
class JointProximity:
    """One joint's standing against its soft limits.

    Attributes:
        near_limit: Whether the remaining travel toward the closer bound is inside the
            margin. True on the bound as well — a joint with no travel left is not less
            near than one with a degree of it.
        blocked_direction: The direction the joint may no longer be jogged, or `NONE`.
    """

    near_limit: bool
    blocked_direction: BlockedDirection


def evaluate_proximity(position: Deg, limit: JointLimit, margin: float) -> JointProximity:
    """Judge one joint's reading against its soft limits.

    A reading outside the set blocks the direction that would take it further out and
    leaves the way back open, which is the only arrangement that lets an operator recover
    a joint parked past its bound. The alternative — blocking both — needs a bus session
    and a person with a hex key to undo.

    Args:
        position: The joint's reading.
        limit: That joint's soft limits, in the same unit.
        margin: Remaining travel, in degrees, below which the joint is reported near.

    Returns:
        (JointProximity) The near-limit flag and the refused direction.
    """
    to_upper = limit.upper_deg.value - position.value
    to_lower = position.value - limit.lower_deg.value
    if to_upper <= 0.0:
        blocked = BlockedDirection.POSITIVE
    elif to_lower <= 0.0:
        blocked = BlockedDirection.NEGATIVE
    else:
        blocked = BlockedDirection.NONE
    return JointProximity(
        near_limit=min(to_upper, to_lower) <= margin,
        blocked_direction=blocked,
    )


__all__ = ["BlockedDirection", "JointProximity", "evaluate_proximity"]
