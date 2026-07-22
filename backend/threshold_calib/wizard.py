"""The calibration wizard: proposal + provenance + the operator no-collision judgment.

This ties the collector and proposer together and enforces the one thing the offline host
cannot fake. `12` FR-SAF-060 makes the calibration *output* the threshold canon, and its
acceptance requires the operator's "no collision occurred" judgment to be recorded — because
the whole method rests on the run having been collision-free, and only a human watching the
arm can attest that. So a calibration is *canonical* only when its residuals came from a
real run and an operator attested no contact. A proposal built from a synthetic residual
stream on a desktop is a demonstration of the math, and `require_canonical` refuses to
present it as canon: THE ONE RULE forbids a measured-threshold green with no measurement.

The per-joint display shows the calibrated effective threshold beside the `12` FR-SAF-020
literature default and its "NOT an OpenArm-measured value" label (imported from WP-1-06), so
a reader always sees the theoretical starting point next to the calibrated result and never
mistakes one for the other.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.safety_bringup.thresholds import default_collision_thresholds
from backend.threshold_calib.constants import (
    PROVENANCE_REAL_ATTESTED,
    PROVENANCE_SYNTHETIC,
)
from backend.threshold_calib.proposer import ThresholdProposal


class CalibrationNotCanonicalError(Exception):
    """Raised when canonical thresholds are requested from an unattested calibration.

    Canon requires a real collision-free run and the operator's no-collision judgment
    (`12` FR-SAF-060). Refusing keeps a synthetic or unattested proposal from being adopted
    as the operating threshold.
    """


@dataclass(frozen=True)
class NoCollisionJudgment:
    """The operator's recorded judgment that a calibration run was collision-free.

    Attributes:
        operator: Identifier of the person who watched the run and rendered the judgment.
        trajectory_id: The representative trajectory the judgment covers.
        attested: True only when the operator affirmed no contact occurred during the run.
        note: Free-text context (e.g. a near-contact the operator chose to accept).
    """

    operator: str
    trajectory_id: str
    attested: bool
    note: str


@dataclass(frozen=True)
class Calibration:
    """A threshold proposal with its provenance and the operator judgment behind it.

    Attributes:
        proposal: The bounded per-joint threshold proposal.
        judgment: The operator no-collision judgment, or None for an unattested run.
        provenance: The provenance label describing where the residuals came from.
        canonical: True only when the residuals were real and the judgment attests no
            collision; the offline synthetic path is never canonical.
    """

    proposal: ThresholdProposal
    judgment: NoCollisionJudgment | None
    provenance: str
    canonical: bool

    def require_canonical(self) -> tuple[float, ...]:
        """Return the effective thresholds only if this calibration is canon.

        Returns:
            (tuple[float, ...]) The per-joint effective thresholds, Nm.

        Raises:
            CalibrationNotCanonicalError: If the calibration is not backed by a real run
                and an attested no-collision judgment.
        """
        if not self.canonical:
            raise CalibrationNotCanonicalError(
                "calibration is not canonical: threshold canon requires a real "
                "collision-free run with an operator-attested no-collision judgment "
                f"(provenance: {self.provenance})"
            )
        return self.proposal.effective_nm()


def synthetic_calibration(proposal: ThresholdProposal) -> Calibration:
    """Wrap an offline proposal as an explicitly non-canonical synthetic calibration.

    The offline host has no powered arm, no live residual and no operator, so a proposal
    built from a synthetic residual stream demonstrates the math but is never canon.

    Args:
        proposal: A proposal computed from synthetic residual statistics.

    Returns:
        (Calibration) The proposal marked synthetic, judgment absent, `canonical=False`.
    """
    return Calibration(
        proposal=proposal, judgment=None, provenance=PROVENANCE_SYNTHETIC, canonical=False
    )


def attested_calibration(proposal: ThresholdProposal, judgment: NoCollisionJudgment) -> Calibration:
    """Wrap a real-run proposal as canon iff the operator attested no collision.

    Args:
        proposal: A proposal computed from a real collision-free residual run.
        judgment: The operator's no-collision judgment for that run.

    Returns:
        (Calibration) Canonical when `judgment.attested`, else a recorded but non-canon
        calibration whose judgment explains why it was not adopted.
    """
    return Calibration(
        proposal=proposal,
        judgment=judgment,
        provenance=PROVENANCE_REAL_ATTESTED,
        canonical=judgment.attested,
    )


@dataclass(frozen=True)
class JointDisplayRow:
    """One joint's row in the effective-threshold display (`12` FR-SAF-020/060).

    Attributes:
        joint_index: Zero-based arm joint index (0 == J1).
        calibrated_nm: The calibration's effective threshold for this joint, Nm.
        default_nm: The `12` FR-SAF-020 literature default for this joint, Nm.
        floor_nm: The ten-LSB physics floor for this joint, Nm.
        effort_cap_nm: The URDF effort limit for this joint, Nm.
        floor_clamped: True when the calibrated value was raised to the floor.
        effort_capped: True when the calibrated value was lowered to the effort cap.
    """

    joint_index: int
    calibrated_nm: float
    default_nm: float
    floor_nm: float
    effort_cap_nm: float
    floor_clamped: bool
    effort_capped: bool


@dataclass(frozen=True)
class ThresholdDisplay:
    """The per-joint effective-threshold display for the wizard UI.

    Attributes:
        rows: One `JointDisplayRow` per joint, in joint order.
        default_label: The `12` FR-SAF-020 provenance label on the literature default,
            imported from WP-1-06 so the "NOT an OpenArm-measured value" wording has one
            source.
        provenance: The calibration's own provenance label.
        canonical: Whether the displayed calibration is canon.
    """

    rows: tuple[JointDisplayRow, ...]
    default_label: str
    provenance: str
    canonical: bool


def effective_threshold_display(calibration: Calibration) -> ThresholdDisplay:
    """Build the per-joint effective-threshold display for a calibration.

    Shows each joint's calibrated effective threshold beside the `12` FR-SAF-020 literature
    default and its provenance label, so the theoretical starting point and the calibrated
    result are always visible together (`12` FR-SAF-060 acceptance, WP-2C-03 contract).

    Args:
        calibration: The calibration to display.

    Returns:
        (ThresholdDisplay) The per-joint rows plus the default and provenance labels.
    """
    default = default_collision_thresholds()
    rows = tuple(
        JointDisplayRow(
            joint_index=joint.joint_index,
            calibrated_nm=joint.effective_nm,
            default_nm=default.thresholds_nm[joint.joint_index],
            floor_nm=joint.floor_nm,
            effort_cap_nm=joint.effort_cap_nm,
            floor_clamped=joint.floor_clamped,
            effort_capped=joint.effort_capped,
        )
        for joint in calibration.proposal.per_joint
    )
    return ThresholdDisplay(
        rows=rows,
        default_label=default.label,
        provenance=calibration.provenance,
        canonical=calibration.canonical,
    )
