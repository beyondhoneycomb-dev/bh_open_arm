"""Named quantities for the numeric Move-to gate (WP-2D-09).

The joint layout and side names are not restated here — they are the one contract the
16-dim action already fixes, so this module imports them from
``backend.cartesian_jog.constants`` rather than spelling a second copy that could drift
(NORM-004: one source per number). What is genuinely local is the human joint numbering
and the operator-facing notes that describe the gate's contract.
"""

from __future__ import annotations

from backend.cartesian_jog.constants import (
    ARM_JOINTS_PER_SIDE,
    BIMANUAL_WIDTH,
    SIDE_WIDTH,
    SIDES,
)

__all__ = [
    "ARM_JOINTS_PER_SIDE",
    "BIMANUAL_WIDTH",
    "FIRST_HUMAN_JOINT_NUMBER",
    "GATE_CONTRACT_NOTE",
    "SIDES",
    "SIDE_WIDTH",
    "arm_slot_base",
]

# Operators and the UI count arm joints from one (joint1..joint7); the 16-dim solution
# and the limit envelope index from zero. The offset lives here so a finding's
# human-facing joint number is derived in one place, not re-added at each call site.
FIRST_HUMAN_JOINT_NUMBER = 1

# The contract this gate guarantees, surfaced so a UI can state why a Move-to did not
# run: execution is reachable only after the limit and (Cartesian) IK-existence checks
# pass. This gate is an admissibility check, not the send-time enforcement point — the
# single send_action gateway remains the backstop for anything this gate admits.
GATE_CONTRACT_NOTE = (
    "A numeric Move-to executes only after its limit check and (for an EE pose) its "
    "IK-solution-existence check pass. A failing input is refused and reported per "
    "reason; it never moves the arm. Real-machine send remains gated downstream by the "
    "single send_action gateway and the dry-run hard-gate."
)


def arm_slot_base(side: str) -> int:
    """Return the 16-dim slot the seven arm joints of ``side`` begin at.

    Right occupies slots 0..6 (arm) and 7 (gripper); left occupies 8..14 (arm) and 15
    (gripper). The same base ``backend.cartesian_jog`` uses for ``arm_joints``, so a
    finding's slot aligns with the jog's committed layout and the soft-limit order.

    Args:
        side: ``"right"`` or ``"left"``.

    Returns:
        (int) The first arm-joint slot for the side.

    Raises:
        ValueError: When ``side`` is neither "right" nor "left".
    """
    if side not in SIDES:
        raise ValueError(f"side must be 'right' or 'left', got {side!r}")
    return 0 if side == "right" else SIDE_WIDTH
