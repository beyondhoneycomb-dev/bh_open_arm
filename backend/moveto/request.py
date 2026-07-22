"""The two numeric Move-to inputs: a joint-space target and an EE-pose target.

FR-MAN-015 admits two ways to command an absolute move by typing numbers: the seven
arm-joint angles, or the end-effector pose. The two are distinct request types, not one
polymorphic blob, because they take different checks — a joint target needs only the
limit check (the joints *are* the configuration), while an EE pose additionally needs
the IK-solution-existence check. Keeping them separate lets the gate dispatch on type
and refuse a malformed input at construction rather than mid-check.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.cartesian_jog import ReferenceFrame, TcpSelection
from backend.moveto.constants import ARM_JOINTS_PER_SIDE, SIDES

# A world/base/tool EE pose is the float[7] [x, y, z, qw, qx, qy, qz] the Cartesian jog
# speaks; the length is fixed by that shared pose convention, named once here.
POSE_WIDTH = 7


def _require_side(side: str) -> str:
    """Return ``side`` if it is a valid arm, else reject.

    Args:
        side: The candidate arm name.

    Returns:
        (str) The validated side.

    Raises:
        ValueError: When ``side`` is neither "right" nor "left".
    """
    if side not in SIDES:
        raise ValueError(f"side must be 'right' or 'left', got {side!r}")
    return side


@dataclass(frozen=True)
class JointMoveTo:
    """A numeric joint-space Move-to: the seven arm-joint angles of one side.

    The gripper is not part of a joint Move-to — it has its own command — so this
    carries exactly the seven arm joints IK would otherwise solve for. A joint target
    is its own configuration, so the gate checks only that it lies inside the limit
    envelope; there is no IK-existence check for a joint input (FR-MAN-015).

    Attributes:
        side: ``"right"`` or ``"left"`` — the arm to move.
        joints_rad: The seven arm-joint targets, radians, joint1..joint7.
    """

    side: str
    joints_rad: tuple[float, ...]

    def __post_init__(self) -> None:
        """Validate the side and the joint-vector width at construction.

        Raises:
            ValueError: When the side is invalid or the vector is not seven-wide.
        """
        _require_side(self.side)
        if len(self.joints_rad) != ARM_JOINTS_PER_SIDE:
            raise ValueError(
                f"joints_rad must be {ARM_JOINTS_PER_SIDE}-wide (arm joints joint1..joint7), "
                f"got {len(self.joints_rad)}"
            )


@dataclass(frozen=True)
class PoseMoveTo:
    """A numeric EE-pose Move-to: an absolute TCP pose to drive one arm to.

    The pose is expressed in a reference frame and about a TCP, matching the Cartesian
    jog's conventions exactly, because the gate proves reachability by handing this
    pose to that jog's IK-existence probe. An EE Move-to takes both checks: the
    IK-existence check (does a solution exist?) and the limit check on the solution it
    would reach.

    Attributes:
        side: ``"right"`` or ``"left"`` — the arm to move.
        target_pose: The float[7] [x, y, z, qw, qx, qy, qz] TCP target.
        frame: The reference frame the pose is given in; None uses the jog default.
        tcp: The tool-center point the pose refers to; None uses the jog default.
    """

    side: str
    target_pose: tuple[float, ...]
    frame: ReferenceFrame | None = None
    tcp: TcpSelection | None = None

    def __post_init__(self) -> None:
        """Validate the side and the pose width at construction.

        Raises:
            ValueError: When the side is invalid or the pose is not seven-wide.
        """
        _require_side(self.side)
        if len(self.target_pose) != POSE_WIDTH:
            raise ValueError(
                f"target_pose must be a {POSE_WIDTH}-vector [x, y, z, qw, qx, qy, qz], "
                f"got {len(self.target_pose)}"
            )

    def pose_array(self) -> np.ndarray:
        """Return the target pose as the float[7] array the jog consumes."""
        return np.asarray(self.target_pose, dtype=float)
