"""Single-joint addressing into the 16-dim bimanual action vector (`WP-2A-01`).

A jog targets exactly one joint of one arm (`04` FR-MAN-008: select arm left/right
and joint J1-J7 or gripper J8). The CTR-ACT `RequestedPositionAction` is a flat
16-dim arm-major vector, so a jog needs a way to name a single joint and resolve it
to a position in that vector. That mapping is this module's whole responsibility.

The arm-major order — left arm first, right arm second — is the order the bimanual
follower assembles and splits the vector (`openarm_follower_oa.py`: both
`get_observation` and `send_action` iterate `("left", ...), ("right", ...)`), so
left occupies indices `[0, SINGLE_ARM_ACTION_DIM)` and right the next block. Left
and right have asymmetric limits and offsets (`04` FR-MAN-008), which is why an
address is bound to a specific arm rather than a bare index.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.jog.config import STEP_SIZES_DEG
from contracts.action import SINGLE_ARM_ACTION_DIM
from contracts.units import Deg

# Joints are numbered J1..J8 (J8 is the gripper), so a joint number is 1-based and
# spans exactly one arm's action width. The per-arm offset is `joint - 1`.
MIN_JOINT_NUMBER = 1
MAX_JOINT_NUMBER = SINGLE_ARM_ACTION_DIM

_OFFERED_STEP_VALUES = frozenset(STEP_SIZES_DEG)


class Arm(Enum):
    """Which arm a jog targets. Left and right have asymmetric limits (FR-MAN-008)."""

    LEFT = "left"
    RIGHT = "right"

    @property
    def base_index(self) -> int:
        """First index this arm occupies in the arm-major bimanual vector.

        Left is the first per-arm block, right the second — the order the bimanual
        follower assembles the vector (`openarm_follower_oa.py` left-then-right).

        Returns:
            (int) 0 for the left arm, `SINGLE_ARM_ACTION_DIM` for the right.
        """
        return 0 if self is Arm.LEFT else SINGLE_ARM_ACTION_DIM


class JogDirection(Enum):
    """Jog sense: `+` increases the joint angle, `−` decreases it (FR-MAN-008)."""

    PLUS = 1
    MINUS = -1


@dataclass(frozen=True)
class JogAddress:
    """A single jog target: one arm, one joint (J1-J7 or gripper J8).

    Attributes:
        arm: Which arm the joint belongs to.
        joint: 1-based joint number, `MIN_JOINT_NUMBER`..`MAX_JOINT_NUMBER`.
    """

    arm: Arm
    joint: int

    def __post_init__(self) -> None:
        """Reject a joint number outside the single-arm range."""
        if not MIN_JOINT_NUMBER <= self.joint <= MAX_JOINT_NUMBER:
            raise ValueError(
                f"joint must be in [{MIN_JOINT_NUMBER}, {MAX_JOINT_NUMBER}], got {self.joint}"
            )

    @property
    def index(self) -> int:
        """Position of this joint in the 16-dim bimanual action vector.

        Returns:
            (int) The arm's base index plus the 0-based joint offset.
        """
        return self.arm.base_index + (self.joint - MIN_JOINT_NUMBER)


def validate_step_size(step: Deg) -> Deg:
    """Return `step` if it is one of the offered step sizes, else reject it.

    The step vocabulary (`config.STEP_SIZES_DEG`) is a contract, not a suggestion:
    a jog step outside it would silently move by an unintended amount, so an
    off-vocabulary size is a `ValueError` rather than a value that runs anyway.

    Args:
        step: The requested step size, in degrees.

    Returns:
        (Deg) The same step, when it is in the offered set.

    Raises:
        ValueError: If `step` is not one of `config.STEP_SIZES_DEG`.
    """
    if step.value not in _OFFERED_STEP_VALUES:
        raise ValueError(f"step size {step.value} deg is not one of {STEP_SIZES_DEG}")
    return step
