"""The link-safety states of the teleop gate and the transitions it forbids.

`WP-3B-10` owns the slice of the `05` §4.2 state machine that link and pose safety
turns on: FOLLOWING (S4), LINK_LOST (S5), IK_FAULT (S7) and the ALIGNING (S3) a
recovery must pass through. The clutch/homing/e-stop states are other packages'; the
enum names the four this gate drives and maps each to its spec S-number.

The forbidden transitions this module exists to make unrepresentable are `05` §4.2
#1 (S5 → S4 direct) and #3 (S7 → S4 direct): a lost link or an IK fault can never
resume following without re-aligning first, because the controller's position is
unknown after the interruption and a 1:1 resume would be a lurch. The only way out of
a hold is an explicit operator re-engage into ALIGNING, and even that is refused while
the deadman lease latch is held — the lease re-arm is the superior handshake
(`WP-2A-02` latch outranks link recovery).
"""

from __future__ import annotations

from enum import Enum


class TeleopLinkState(Enum):
    """The link-safety state of the teleop gate, each mapped to its `05` §4.2 S-number.

    Attributes are the S-number and a stable name; `is_hold` marks the states whose
    action is a position hold, from which the only exit is an explicit re-engage.
    """

    ALIGNING = "S3"
    FOLLOWING = "S4"
    LINK_LOST = "S5"
    IK_FAULT = "S7"

    @property
    def is_hold(self) -> bool:
        """Whether this state holds position and refuses an implicit resume."""
        return self in (TeleopLinkState.LINK_LOST, TeleopLinkState.IK_FAULT)


class ForbiddenTransitionError(RuntimeError):
    """Raised when a caller attempts a `05` §4.2 forbidden state transition.

    The gate never performs one itself; this guards the public re-engage entry point
    so that a caller trying to skip ALIGNING (resume following straight out of a hold)
    is refused rather than silently obeyed.
    """


class RearmRequiredError(RuntimeError):
    """Raised when a re-engage is attempted while the deadman lease latch is held.

    `WP-3B-10` contract: link recovery is not re-arming. While the `WP-2A-02` lease is
    latched, entry into ALIGNING is refused until the operator completes the deadman
    re-arm handshake, which clears the latch. The lease latch is the superior gate.
    """


class LinkNotLiveError(RuntimeError):
    """Raised when a re-engage is attempted while the VR link is still lost.

    `05` §4.2/S5: the exit from a lost link is "VR returned AND explicit re-engage".
    An operator cannot align to a link that is not delivering fresh frames.
    """
