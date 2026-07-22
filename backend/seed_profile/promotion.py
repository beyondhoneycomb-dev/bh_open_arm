"""The explicit v1->v2 promotion path (FR-SAF-031/067, `02b` WP-2B-10 acceptance ②).

Promotion is two deliberate steps with a human gate between them:

1. `build_promotion_report` runs WP-2B-01's `convert_v1_to_v2` and computes the per-joint
   relative error between the v1 seed pose and its v2 conversion. It activates nothing. The
   report exists so an operator sees exactly what the conversion changes — joint2's +pi/2 shift
   shows up as a large relative error there and ~zero elsewhere, the fingerprint that the shift
   landed and is confined to the shoulder.
2. `promote` activates the converted asset, but only against an `Approval` whose digest matches
   the report's. A blank or mismatched approval — one that did not acknowledge this exact report
   — is refused. There is no path from seed to an activated v2 asset that skips the report the
   approval is bound to.

The activated result is a `LoadedDynamicsAsset` that has passed WP-2B-01's strict provenance
gate, so it is a first-class v2 asset, not a v1 asset in disguise.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from backend.dynamics.asset import LoadedDynamicsAsset, convert_v1_to_v2, load_safety_params
from backend.dynamics.converter import JointFrameConverter
from backend.dynamics.provenance import Provenance
from backend.seed_profile.constants import (
    DIGEST_ALGORITHM,
    DIGEST_DISPLAY_LEN,
    RELATIVE_ERROR_EPSILON_RAD,
    SEED_POSE_FIELD,
)
from backend.seed_profile.errors import PromotionNotApprovedError
from backend.seed_profile.profile import PROVENANCE_KEY, SeedProfile

_UNDEFINED_RELATIVE = "—"


@dataclass(frozen=True)
class JointRelativeError:
    """The v1->v2 change at one joint, shown to the operator before approval.

    Attributes:
        joint_index: Zero-based joint index.
        v1_value: The v1 seed value at this joint (radians).
        v2_value: The v2 value after conversion (radians).
        absolute_error: `|v2 - v1|`.
        relative_error: `|v2 - v1| / |v1|`, or None when `|v1|` is below the epsilon floor and the
            ratio would be a spurious infinity.
    """

    joint_index: int
    v1_value: float
    v2_value: float
    absolute_error: float
    relative_error: float | None


@dataclass(frozen=True)
class PromotionReport:
    """A computed but not-yet-activated v1->v2 promotion (acceptance ②, first half).

    Attributes:
        seed_provenance: The v1 seed's origin stamp.
        target_provenance: The v2 stamp the conversion carries.
        per_joint: Per-joint relative error, one entry per arm joint.
        converted_asset: A read-only view of the full v2 asset (payload plus v2 provenance).
        digest: Tamper-evident digest of the report an approval must acknowledge.
    """

    seed_provenance: Provenance
    target_provenance: Provenance
    per_joint: tuple[JointRelativeError, ...]
    converted_asset: Mapping[str, Any]
    digest: str

    @property
    def activated(self) -> bool:
        """A report never activates by itself — activation is `promote` with an approval."""
        return False

    def format_table(self) -> str:
        """Render the per-joint relative-error table for operator review.

        Returns:
            (str) A fixed-width table; the relative-error column reads '—' where `|v1|` is below
                the epsilon floor and the ratio is undefined.
        """
        header = "  ".join(
            (
                f"{'joint':>5}",
                f"{'v1 (rad)':>12}",
                f"{'v2 (rad)':>12}",
                f"{'abs err':>12}",
                f"{'rel err':>10}",
            )
        )
        lines = [header, "-" * len(header)]
        for row in self.per_joint:
            if row.relative_error is None:
                relative = f"{_UNDEFINED_RELATIVE:>10}"
            else:
                relative = f"{row.relative_error * 100.0:>9.2f}%"
            lines.append(
                f"{row.joint_index:>5}  {row.v1_value:>12.6f}  {row.v2_value:>12.6f}  "
                f"{row.absolute_error:>12.6f}  {relative}"
            )
        return "\n".join(lines)


@dataclass(frozen=True)
class Approval:
    """An operator's explicit acknowledgement of a specific promotion report (FR-SAF-067).

    Attributes:
        operator: Who approved the promotion.
        acknowledged_report_digest: The digest of the report seen; binds this approval to that
            exact report so a blank or stale approval cannot activate a different conversion.
        approved_on: When the approval was given (ISO-8601).
    """

    operator: str
    acknowledged_report_digest: str
    approved_on: str

    def __post_init__(self) -> None:
        """Refuse an approval with any blank field.

        Raises:
            PromotionNotApprovedError: If operator, digest, or date is empty or whitespace.
        """
        for field_name in ("operator", "acknowledged_report_digest", "approved_on"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise PromotionNotApprovedError(
                    f"approval field {field_name!r} is required and must be non-empty; an implicit "
                    "or blank approval cannot activate a v1->v2 promotion (FR-SAF-067)"
                )


@dataclass(frozen=True)
class PromotedProfile:
    """An activated v2 asset, with the approval and report that authorised it (acceptance ②).

    Attributes:
        asset: The v2 asset, past WP-2B-01's strict provenance gate.
        approval: The explicit approval that authorised activation.
        report_digest: The digest of the report the approval acknowledged.
    """

    asset: LoadedDynamicsAsset
    approval: Approval
    report_digest: str

    @property
    def activated(self) -> bool:
        """A promoted profile is, by construction, activated."""
        return True

    def as_v2_mapping(self) -> dict[str, Any]:
        """Return the activated asset as a full v2 asset mapping (payload plus v2 provenance)."""
        mapping = dict(self.asset.payload)
        mapping[PROVENANCE_KEY] = self.asset.provenance.to_dict()
        return mapping


def build_promotion_report(
    seed: SeedProfile,
    converter: JointFrameConverter,
    target_provenance: Provenance,
) -> PromotionReport:
    """Convert the seed to v2 and report per-joint relative error, activating nothing.

    Args:
        seed: The read-only v1 seed.
        converter: WP-2B-01's v1->v2 joint-frame map for this arm.
        target_provenance: The v2 stamp (robot_version "2.0") to carry on the conversion.

    Returns:
        (PromotionReport) The per-joint diff plus the converted (not yet activated) v2 asset.

    Raises:
        DynamicsConversionError: If the seed carries an unconvertible item or the target stamp is
            not v2 (raised by `convert_v1_to_v2`).
    """
    converted = convert_v1_to_v2(seed.as_v1_mapping(), converter, target_provenance)

    v1_pose = seed.seed_pose()
    v2_pose = tuple(float(value) for value in converted.payload[SEED_POSE_FIELD])
    per_joint = tuple(
        _joint_error(index, v1, v2)
        for index, (v1, v2) in enumerate(zip(v1_pose, v2_pose, strict=True))
    )

    converted_asset = dict(converted.payload)
    converted_asset[PROVENANCE_KEY] = converted.provenance.to_dict()
    digest = _report_digest(seed.provenance, target_provenance, per_joint)

    return PromotionReport(
        seed_provenance=seed.provenance,
        target_provenance=target_provenance,
        per_joint=per_joint,
        converted_asset=converted_asset,
        digest=digest,
    )


def promote(report: PromotionReport, approval: Approval) -> PromotedProfile:
    """Activate a promotion report — refused unless the approval acknowledges this exact report.

    Args:
        report: The report an operator reviewed.
        approval: The explicit approval; its `acknowledged_report_digest` must equal the report's.

    Returns:
        (PromotedProfile) The activated v2 asset with its authorising approval.

    Raises:
        PromotionNotApprovedError: If the approval does not match this report's digest.
    """
    if approval.acknowledged_report_digest != report.digest:
        raise PromotionNotApprovedError(
            "approval does not acknowledge this promotion report: approved digest "
            f"{approval.acknowledged_report_digest!r} != report digest {report.digest!r}; an "
            "approval must be bound to the exact per-joint diff it authorises (FR-SAF-067)"
        )
    # Re-run the strict gate at activation: the activated asset is verified v2 at the moment it
    # becomes usable, not merely at the moment the report was built.
    asset = load_safety_params(dict(report.converted_asset), strict=True)
    return PromotedProfile(asset=asset, approval=approval, report_digest=report.digest)


def _joint_error(index: int, v1_value: float, v2_value: float) -> JointRelativeError:
    """Build one joint's relative-error row, marking the ratio undefined near a zero v1."""
    absolute = abs(v2_value - v1_value)
    if abs(v1_value) < RELATIVE_ERROR_EPSILON_RAD:
        relative: float | None = None
    else:
        relative = absolute / abs(v1_value)
    return JointRelativeError(
        joint_index=index,
        v1_value=v1_value,
        v2_value=v2_value,
        absolute_error=absolute,
        relative_error=relative,
    )


def _report_digest(
    seed_provenance: Provenance,
    target_provenance: Provenance,
    per_joint: tuple[JointRelativeError, ...],
) -> str:
    """Digest the material content of a report so an approval can be bound to it.

    The digest covers both provenance stamps and every per-joint (v1, v2) pair, so a changed
    conversion or a changed origin yields a different digest and any approval of the old report
    stops matching.
    """
    material = {
        "seed_provenance": seed_provenance.to_dict(),
        "target_provenance": target_provenance.to_dict(),
        "per_joint": [
            [row.joint_index, repr(row.v1_value), repr(row.v2_value)] for row in per_joint
        ],
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.new(DIGEST_ALGORITHM, encoded).hexdigest()[:DIGEST_DISPLAY_LEN]
