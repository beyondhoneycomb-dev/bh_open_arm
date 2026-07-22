"""The calibration transform chain and its offset double-add / miss detector.

`04` FR-MAN-058 and `02` FR-CON-033 fix the manual-motion transform chain as
`q_user(F_URDF) → +joint_offsets → q_motor(rad) → MIT 16-bit q_uint`, and require
that the offset be applied at **exactly one point** in the pipeline (`04`
FR-MAN-004: "정확히 한 지점"). The system adopted convention (a) (`02` §2.9,
Q-10 [해결]): the zero lives in the motor NV (0xFE) at the URDF-zero rest pose, so
`q_lerobot(deg) = degrees(q_URDF)` and `joint_offsets` (L2) is **not** added in the
adapter — the expected application count is therefore `0`. The mechanism here does
not hard-code that: it takes the expected count as an input so an option-(b)
deployment that adds the offset once can set it to `1`.

Why record the whole chain and not just the endpoints: when the declared offset is
zero (convention a), a double-add and a miss are *numerically* invisible, so a
value-only check would be vacuously green. Two independent axes close that hole:

- **Structural** — `offset_applications`, how many pipeline stages actually added
  the offset, must equal the declared expected count. This catches a regression
  that re-introduces or drops an application even when the offset value is zero.
- **Numeric** — `q_motor` must equal `q_user + offset_applications · joint_offset`
  within tolerance. This catches an offset baked into the value without its stage
  incrementing the counter (a counter the pipeline bypassed), which the structural
  axis alone would miss.

A chain that fails either axis is a fault the audit ring blocks immediately
(`04` FR-MAN-058: "즉시 감지·차단"); it is not merely logged.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from contracts.units import Rad

# Numeric slack, in radians, for the "q_motor == q_user + n·offset" residual check.
# Well below any real per-joint offset (the smallest URDF zero offsets are on the
# order of degrees) yet far above float round-trip noise, so it separates a genuine
# extra/dropped offset from arithmetic error without ever masking one.
OFFSET_RESIDUAL_TOLERANCE_RAD = 1e-6

# The application count convention (a) implies (`02` §2.9): the adapter adds no
# software joint offset, so the offset is applied zero times. Option (b) would set
# this to 1. It is the *expected* count every recorded chain is checked against.
DECISION_A_OFFSET_APPLICATIONS = 0


class OffsetFault(Enum):
    """Why a recorded transform chain failed the offset-integrity check.

    Kept distinct so the audit dump attributes a stop to the specific failure — a
    double-add and a miss have opposite fixes, and a residual mismatch points at a
    bypassed application counter rather than at the count itself.
    """

    DOUBLE_ADD = "double_add"
    MISSED = "missed"
    RESIDUAL_MISMATCH = "residual_mismatch"


@dataclass(frozen=True)
class JointTransform:
    """One joint's recorded pass through the calibration transform chain.

    Every stage of `q_user(F_URDF) → +joint_offset → q_motor(rad) → q_uint` is kept
    so a double-add or miss is reconstructable after the fact (`04` FR-MAN-058, `02`
    FR-CON-033). `q_uint` is the actual 16-bit MIT value the CAN layer produced; it
    is recorded for the post-event dump but is not part of the offset check, which
    lives entirely in the radian domain where the offset is added.

    Attributes:
        q_user_rad: The operator-facing F_URDF joint angle, radians (offset-free).
        joint_offset_rad: The declared per-joint offset (zero under convention a).
        q_motor_rad: The motor-frame command angle the pipeline produced, radians.
        q_uint: The 16-bit MIT-encoded position the CAN layer actually emitted.
        offset_applications: How many pipeline stages added `joint_offset_rad`.
    """

    q_user_rad: Rad
    joint_offset_rad: Rad
    q_motor_rad: Rad
    q_uint: int
    offset_applications: int


@dataclass(frozen=True)
class OffsetVerdict:
    """The offset-integrity outcome for one chain of joints.

    Attributes:
        fault: The first fault found, or None when every joint is consistent.
        joint_index: The joint the fault was found at, or None on a clean chain.
    """

    fault: OffsetFault | None
    joint_index: int | None

    @property
    def ok(self) -> bool:
        """Whether the chain applied the offset exactly as declared.

        Returns:
            (bool) True when no joint faulted.
        """
        return self.fault is None


_CLEAN = OffsetVerdict(fault=None, joint_index=None)


def check_joint(
    joint: JointTransform,
    expected_applications: int,
    tolerance_rad: float,
) -> OffsetFault | None:
    """Return the offset fault for one joint, or None when it is consistent.

    Args:
        joint: The recorded transform for this joint.
        expected_applications: How many times the offset should have been applied.
        tolerance_rad: Slack for the `q_motor == q_user + n·offset` residual.

    Returns:
        (OffsetFault | None) The fault, or None when both axes agree.
    """
    if joint.offset_applications != expected_applications:
        if joint.offset_applications > expected_applications:
            return OffsetFault.DOUBLE_ADD
        return OffsetFault.MISSED
    applied = joint.offset_applications * joint.joint_offset_rad.value
    residual = joint.q_motor_rad.value - (joint.q_user_rad.value + applied)
    if abs(residual) > tolerance_rad:
        return OffsetFault.RESIDUAL_MISMATCH
    return None


def check_chain(
    transforms: tuple[JointTransform, ...],
    expected_applications: int = DECISION_A_OFFSET_APPLICATIONS,
    tolerance_rad: float = OFFSET_RESIDUAL_TOLERANCE_RAD,
) -> OffsetVerdict:
    """Check a full joint chain for an offset double-add or miss.

    The first faulting joint decides the verdict, because one bad joint is already
    grounds to block — the audit does not need to enumerate the rest to know the
    command must not proceed.

    Args:
        transforms: One `JointTransform` per joint, in joint order.
        expected_applications: How many times the offset should have been applied
            (0 under convention a, `02` §2.9).
        tolerance_rad: Slack for the residual check.

    Returns:
        (OffsetVerdict) The first fault and its joint index, or a clean verdict.
    """
    for index, joint in enumerate(transforms):
        fault = check_joint(joint, expected_applications, tolerance_rad)
        if fault is not None:
            return OffsetVerdict(fault=fault, joint_index=index)
    return _CLEAN


class OffsetIntegrityError(RuntimeError):
    """Raised when a recorded transform chain double-added or missed the offset.

    The audit ring raises this the instant it records such a chain, so the offending
    command is blocked rather than logged and forgotten (`04` FR-MAN-058). It carries
    the verdict so the caller and the dump can attribute the stop.

    Attributes:
        verdict: The offending chain's offset verdict (fault and joint index).
    """

    def __init__(self, verdict: OffsetVerdict) -> None:
        """Build the error from the verdict that triggered it.

        Args:
            verdict: The non-ok verdict `check_chain` returned.
        """
        self.verdict = verdict
        super().__init__(
            f"offset {verdict.fault.value if verdict.fault else 'fault'} "
            f"at joint {verdict.joint_index}"
        )
