"""The six action/observation channels as unit-tagged types (CTR-ACT@v1).

SPINE §6 (00 §8.3) freezes six channels, and their separation is the contract:

- `RequestedPositionAction` and `AcceptedPositionAction` are both position-only
  (`Deg`), 16-dim bimanual. Recording only the accepted (post-clamp) action erases
  the request, which makes intervention and clamp saturation undebuggable, so both
  exist and both are kept (00 §8.3).
- `ExecutedMitCommand` is the MIT frame the scheduler actually emitted. It is an
  AUDIT record — never a training input. Its physical fields carry CTR-UNIT tags
  (q=`Rad`, dq=`RadPerSec`, tau=`Nm`, 12 §2.7); kp/kd are MIT gains, dimensionless
  at this boundary and not CTR-UNIT quantities.
- `SafetyOverride` explains why the accepted action differs from the request.
- `RawObservation` and `TrainingFeatureProjection` are declared in
  `contracts.action.observation` and `contracts.action.schema`, which reuse the
  frozen unit_tags observation layout.

Every physical quantity is a tag type, not a bare float: a position is `Deg`, an
executed torque is `Nm`, and mixing them is a static type error rather than a
57.3x-wrong command that runs anyway.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from contracts.units import Deg, Nm, Rad, RadPerSec

# Bimanual position action width: 8 motors per arm, two arms (10 §2.3). The single
# 16 and the observation's 48 are different axes — 16 is position-only action, 48
# is pos/vel/torque observation — so they are named apart to stop the two being
# conflated at a call site.
BIMANUAL_ACTION_DIM = 16
SINGLE_ARM_ACTION_DIM = 8

# The MIT command is a fixed 5-tuple {kp, kd, q, dq, tau} (12 §2.7).
MIT_COMMAND_FIELDS = 5


class ClampReason(Enum):
    """Why the accepted action was clamped away from the request (12 FR-SAF-074).

    Recorded on `SafetyOverride` so a post-clamp-only dataset cannot hide the
    reason a request was altered.
    """

    NONE = "none"
    JOINT_LIMIT = "joint_limit"
    TORQUE_LIMIT = "torque_limit"
    STALE_SOURCE = "stale_source"
    SAFETY_LATCH = "safety_latch"


@dataclass(frozen=True)
class RequestedPositionAction:
    """The producer's pre-clamp position request, 16-dim bimanual, degrees.

    Position-only (10 FR-TRN-066). This is NOT the dataset action; it is kept
    beside the accepted action purely so intervention and saturation are
    debuggable (00 §8.3).

    Attributes:
        values: One `Deg` per bimanual joint, arm-major, length `BIMANUAL_ACTION_DIM`.
    """

    values: tuple[Deg, ...]

    def __post_init__(self) -> None:
        """Reject a width other than the frozen bimanual action dimension."""
        if len(self.values) != BIMANUAL_ACTION_DIM:
            raise ValueError(
                f"requestedPositionAction must be {BIMANUAL_ACTION_DIM}-dim, got {len(self.values)}"
            )


@dataclass(frozen=True)
class AcceptedPositionAction:
    """The post-clamp position actually admitted — the dataset `action`.

    Position-only, produced by clamping the request to the LeRobot joint_limits
    (01 FR-SYS-016). This is the sole training target among the action channels;
    the type is `Deg`, so a torque (`Nm`) supplied here is a static type error.

    Attributes:
        values: One `Deg` per bimanual joint, arm-major, length `BIMANUAL_ACTION_DIM`.
    """

    values: tuple[Deg, ...]

    def __post_init__(self) -> None:
        """Reject a width other than the frozen bimanual action dimension."""
        if len(self.values) != BIMANUAL_ACTION_DIM:
            raise ValueError(
                f"acceptedPositionAction must be {BIMANUAL_ACTION_DIM}-dim, got {len(self.values)}"
            )


@dataclass(frozen=True)
class ExecutedMitCommand:
    """The MIT frame the scheduler emitted, recorded for AUDIT only (00 §8.3).

    Never a training input. The physical fields carry their CAN-boundary units
    (12 §2.7): q in `Rad`, dq in `RadPerSec`, tau in `Nm`. kp and kd are MIT gains
    (stiffness and damping), scalar at this boundary and deliberately not modelled
    as CTR-UNIT physical quantities — they cross no unit boundary.

    Attributes:
        kp: MIT proportional (stiffness) gain.
        kd: MIT derivative (damping) gain.
        q: Commanded joint position, radians.
        dq: Commanded joint velocity, radians per second.
        tau: Commanded feed-forward torque, newton-metres. AUDIT — must not reach
            any action target.
    """

    kp: float
    kd: float
    q: Rad
    dq: RadPerSec
    tau: Nm


@dataclass(frozen=True)
class SafetyOverride:
    """Why the accepted action differs from the request (12 FR-SAF-074).

    Diagnostic metadata, never a training target.

    Attributes:
        override_active: Whether a safety override altered the action this tick.
        clamp_reason: The reason the request was clamped.
        stale: Whether the source mailbox was stale this tick.
        latched: Whether a safety latch is held (until operator ack).
    """

    override_active: bool
    clamp_reason: ClampReason
    stale: bool
    latched: bool
