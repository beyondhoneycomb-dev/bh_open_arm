"""The jog-path clamp reasons and their mapping onto the frozen audit reason.

WP-2A-03 shapes a jog target before it reaches the single `send_action` gateway
(`11` NFR-INF-008, the un-bypassable enforcement point). Three producer-side clamps
run in the shaping, and this enum names which one altered a command — one distinct
value each — so a clamp counter can attribute a saturation instead of losing it to
LeRobot's silent `logger.debug` clip (`04` FR-MAN-013, acceptance ③).

These are producer-side diagnostic reasons, finer than the frozen `ClampReason`
(`CTR-ACT@v1`) the audit channel carries. The mapping below is the one Wave-1
already applies to its own finer `SafetyReason`: every position or step clamp is a
`JOINT_LIMIT` at the audit boundary. The finer vocabulary lives here, not in the
frozen contract, precisely so the contract is not reopened for a producer-side
counter key.
"""

from __future__ import annotations

from enum import Enum

from contracts.action import ClampReason


class JogClampReason(Enum):
    """Which jog-path clamp altered a command — one distinct value per stage.

    A merged reason is forbidden for the same argument Wave-1 forbids one: a counter
    that cannot tell a request beyond the mechanical envelope (a producer fault) from
    one merely beyond the operational envelope (a normal operating clamp) cannot
    attribute a saturation.
    """

    MECHANICAL_LIMIT = "mechanical_limit"
    OPERATIONAL_LIMIT = "operational_limit"
    STEP_CAP = "step_cap"


# Every jog-path clamp is a joint-limit-class alteration at the CTR-ACT audit
# boundary — the same mapping Wave-1's `_REASON_TO_CLAMP` applies to its position
# and step-delta reasons. Kept as an explicit table so a future divergence has one
# place to live rather than a constant buried in a call site.
_REASON_TO_CLAMP: dict[JogClampReason, ClampReason] = {
    JogClampReason.MECHANICAL_LIMIT: ClampReason.JOINT_LIMIT,
    JogClampReason.OPERATIONAL_LIMIT: ClampReason.JOINT_LIMIT,
    JogClampReason.STEP_CAP: ClampReason.JOINT_LIMIT,
}


def to_clamp_reason(reason: JogClampReason) -> ClampReason:
    """Map a jog-path clamp reason onto the frozen CTR-ACT audit reason.

    Args:
        reason: The finer jog-path reason a stage recorded.

    Returns:
        (ClampReason) The frozen `CTR-ACT@v1` reason the audit channel carries.
    """
    return _REASON_TO_CLAMP[reason]
