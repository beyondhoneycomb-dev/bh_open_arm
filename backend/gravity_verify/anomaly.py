"""The joint-2 residual-anomaly check (②): the +pi/2-shift fingerprint, as real logic.

The failure this catches is silent. If WP-2B-01's `+pi/2` joint2 shift was not applied, the
modelled shoulder gravity has sin and cos swapped (spec 12 §2.6), so the joint2 residual against
a real measurement is large while every other joint stays small — and nothing raises an error.
This check is the only thing that turns that into a signal: it compares joint2's residual
magnitude against its peers and flags it as the fingerprint when joint2 dominates.

The test is deliberately two-sided so it is not a rubber stamp. Joint2 must beat the *median*
of the other joints by a ratio (so one incidentally-large wrist joint cannot mask it) AND clear
an absolute floor (so sub-Nm scatter, where a large ratio is just noise, does not trip it). A
well-converted model leaves joint2 comparable to its peers and is not flagged; an un-shifted
model is. A positive result is the WP-2B-03 negative branch: WP-2B-01 is SUPERSEDED and re-run.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from backend.gravity_verify.constants import (
    J2_ANOMALY_ABS_FLOOR_NM,
    J2_ANOMALY_RATIO,
    JOINT2_INDEX,
)
from backend.gravity_verify.residual import ResidualTable


@dataclass(frozen=True)
class J2AnomalyResult:
    """The outcome of the joint-2 residual-anomaly check.

    Attributes:
        joint2_rms_nm: Joint2's RMS residual across the grid, Nm.
        peer_median_rms_nm: The median RMS residual of the other six joints, Nm — the peer
            baseline joint2 is judged against.
        ratio: `joint2_rms_nm / peer_median_rms_nm`, or infinity when the peer baseline is zero
            and joint2 is not.
        ratio_threshold: The ratio above which joint2 counts as dominating (with the floor).
        abs_floor_nm: The absolute joint2 residual floor below which a large ratio is treated as
            noise, not a fingerprint.
        is_anomalous: True when joint2's residual reads as the un-shifted +pi/2 fingerprint.
    """

    joint2_rms_nm: float
    peer_median_rms_nm: float
    ratio: float
    ratio_threshold: float
    abs_floor_nm: float
    is_anomalous: bool


def detect_j2_anomaly(
    table: ResidualTable,
    ratio_threshold: float = J2_ANOMALY_RATIO,
    abs_floor_nm: float = J2_ANOMALY_ABS_FLOOR_NM,
) -> J2AnomalyResult:
    """Flag a joint-2 residual that reads as the un-applied +pi/2-shift fingerprint (②).

    Args:
        table: The residual table from the harness.
        ratio_threshold: How far joint2 must exceed the peer median to count as dominating.
        abs_floor_nm: The absolute joint2 residual required before the ratio is trusted.

    Returns:
        (J2AnomalyResult) The joint2 magnitude, the peer baseline, the ratio, and the verdict.
    """
    joint2 = table.joint_stats[JOINT2_INDEX].rms_nm
    peers = [stat.rms_nm for stat in table.joint_stats if stat.joint_index != JOINT2_INDEX]
    peer_median = median(peers)
    ratio = _dominance_ratio(joint2, peer_median)

    is_anomalous = joint2 >= abs_floor_nm and ratio >= ratio_threshold
    return J2AnomalyResult(
        joint2_rms_nm=joint2,
        peer_median_rms_nm=peer_median,
        ratio=ratio,
        ratio_threshold=ratio_threshold,
        abs_floor_nm=abs_floor_nm,
        is_anomalous=is_anomalous,
    )


def _dominance_ratio(joint2: float, peer_median: float) -> float:
    """Return joint2's residual as a multiple of the peer median, guarding a zero baseline.

    A zero peer baseline with a non-zero joint2 is unbounded dominance (infinity); with a zero
    joint2 too it is no dominance (zero), never a division error.
    """
    if peer_median > 0.0:
        return joint2 / peer_median
    return float("inf") if joint2 > 0.0 else 0.0
