"""Turn collected residual statistics into per-joint collision thresholds (WP-2C-03).

The two rules of `12` FR-SAF-060 live here: `max + 3sigma` and 105-110 % of the residual
maximum. Both operate on the collected collision-free statistics, and both are then bounded
by the two physics limits WP-1-06 owns (`12` FR-SAF-019): a proposal is raised to the
ten-LSB floor when the residual envelope sits below quantisation noise, and lowered to the
URDF effort limit when it exceeds peak torque. The floor and cap are imported, never
re-derived — a threshold below the floor cannot be distinguished from noise and a threshold
above effort can never trip, so the wizard must not emit either, and the numbers that define
them belong to exactly one module.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.safety_bringup.constants import URDF_EFFORT_LIMIT_NM
from backend.safety_bringup.thresholds import floor_for_joint
from backend.threshold_calib.collector import ResidualStats
from backend.threshold_calib.constants import (
    METHOD_MAX_PLUS_SIGMA,
    METHOD_NOMINAL_SCALED,
    NOMINAL_SCALE_MAX,
    NOMINAL_SCALE_MIN,
    SIGMA_MULTIPLE,
)


class ProposalError(Exception):
    """Raised when a proposal is requested with an out-of-range or unknown parameter."""


@dataclass(frozen=True)
class PerJointThreshold:
    """One joint's proposed collision threshold and the bounds that shaped it.

    Attributes:
        joint_index: Zero-based arm joint index (0 == J1).
        raw_nm: The unbounded statistic the proposal rule produced, Nm.
        effective_nm: The proposal after the floor and effort cap, the value that ships, Nm.
        floor_nm: The ten-LSB physics floor for this joint, Nm (`12` FR-SAF-019).
        effort_cap_nm: The URDF effort limit for this joint, Nm (`12` FR-SAF-019).
        floor_clamped: True when the raw statistic sat below the floor and was raised to it.
        effort_capped: True when the raw statistic exceeded effort and was lowered to it.
    """

    joint_index: int
    raw_nm: float
    effective_nm: float
    floor_nm: float
    effort_cap_nm: float
    floor_clamped: bool
    effort_capped: bool


@dataclass(frozen=True)
class ThresholdProposal:
    """A full per-joint threshold proposal and the rule that produced it.

    Attributes:
        method: Which `12` FR-SAF-060 rule produced it (`max_plus_3sigma`/`nominal_scaled`).
        nominal_scale: The margin used for the nominal-scaled rule, else None.
        per_joint: One `PerJointThreshold` per joint, in joint order.
    """

    method: str
    nominal_scale: float | None
    per_joint: tuple[PerJointThreshold, ...]

    def effective_nm(self) -> tuple[float, ...]:
        """Return the shipping per-joint effective thresholds, Nm.

        Returns:
            (tuple[float, ...]) The floor- and cap-bounded thresholds in joint order.
        """
        return tuple(joint.effective_nm for joint in self.per_joint)


def _bounded(joint_index: int, raw_nm: float) -> PerJointThreshold:
    """Apply the ten-LSB floor and the URDF effort cap to one raw statistic.

    Args:
        joint_index: Zero-based arm joint index.
        raw_nm: The unbounded statistic the proposal rule produced, Nm.

    Returns:
        (PerJointThreshold) The bounded threshold and the flags recording which bound bit.
    """
    floor = floor_for_joint(joint_index)
    cap = URDF_EFFORT_LIMIT_NM[joint_index]
    floor_clamped = raw_nm < floor
    effort_capped = raw_nm > cap
    effective = min(max(raw_nm, floor), cap)
    return PerJointThreshold(
        joint_index=joint_index,
        raw_nm=raw_nm,
        effective_nm=effective,
        floor_nm=floor,
        effort_cap_nm=cap,
        floor_clamped=floor_clamped,
        effort_capped=effort_capped,
    )


def propose_max_plus_sigma(stats: tuple[ResidualStats, ...]) -> ThresholdProposal:
    """Propose thresholds by the `max + 3sigma` rule (`12` FR-SAF-060).

    Args:
        stats: Per-joint collision-free residual statistics from the collector.

    Returns:
        (ThresholdProposal) The bounded per-joint proposal tagged `max_plus_3sigma`.
    """
    per_joint = tuple(
        _bounded(stat.joint_index, stat.max_abs_nm + SIGMA_MULTIPLE * stat.sigma_nm)
        for stat in stats
    )
    return ThresholdProposal(method=METHOD_MAX_PLUS_SIGMA, nominal_scale=None, per_joint=per_joint)


def propose_nominal_scaled(stats: tuple[ResidualStats, ...], scale: float) -> ThresholdProposal:
    """Propose thresholds by scaling the residual maximum 105-110 % (`12` FR-SAF-060).

    Args:
        stats: Per-joint collision-free residual statistics from the collector.
        scale: The margin on the residual maximum, within [1.05, 1.10].

    Returns:
        (ThresholdProposal) The bounded per-joint proposal tagged `nominal_scaled`.

    Raises:
        ProposalError: If the scale is outside the admitted 105-110 % band.
    """
    if not NOMINAL_SCALE_MIN <= scale <= NOMINAL_SCALE_MAX:
        raise ProposalError(
            f"nominal scale {scale} outside [{NOMINAL_SCALE_MIN}, {NOMINAL_SCALE_MAX}]"
        )
    per_joint = tuple(_bounded(stat.joint_index, stat.max_abs_nm * scale) for stat in stats)
    return ThresholdProposal(method=METHOD_NOMINAL_SCALED, nominal_scale=scale, per_joint=per_joint)
