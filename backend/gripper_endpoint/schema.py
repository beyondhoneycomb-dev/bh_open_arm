"""The gripper endpoint-capture + sign-mirror record shape and its load-time schema.

Three record pieces, all validated the moment they are constructed so a bad config
is refused at load rather than surfacing later as a gripper that silently never opens
(FR-MAN-017, FR-TEL-059):

* `GripperEndpointCapture` — one side's two hand-captured endpoint rads, the anchors
  of the norm[0,1] linear map (FR-MAN-016). It can be built from a per-arm
  `OpenArmCalibration` (`from_calibration`), which is where those rads live on the
  real robot, so this WP reads the CTR-CAL endpoints rather than re-capturing them.
* `GripperLimits` — one side's `(lo, hi)` joint limits, the subject of the sign
  mirror.
* `GripperMirrorRecord` — the persisted cross-arm record. Its invariant is the one
  a single-arm calibration cannot state: `left_limits == (-hi_right, -lo_right)`
  (FR-MAN-017), plus a per-unit force cap and a speed cap clamped to the DM4310
  register V_MAX.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from backend.calibration.schema import OpenArmCalibration
from backend.gripper_endpoint.constants import (
    MIN_ENDPOINT_SEPARATION_RAD,
    MIRROR_TOLERANCE_RAD,
    SCHEMA_VERSION,
    SIDE_LEFT,
    SIDE_RIGHT,
    SIDES,
)
from backend.gripper_endpoint.errors import GripperConfigError
from backend.gripper_endpoint.posforce import clamp_speed_rad_s, validate_torque_pu


def _require_side(side: str) -> str:
    """Return `side` if it is a known arm side, else refuse.

    Args:
        side: A candidate side token.

    Returns:
        (str) The validated side.

    Raises:
        GripperConfigError: If `side` is not `left` or `right`.
    """
    if side not in SIDES:
        raise GripperConfigError(f"side must be one of {SIDES}, got {side!r}")
    return side


@dataclass
class GripperEndpointCapture:
    """One side's captured open/close endpoint rads — the norm[0,1] map anchors.

    Attributes:
        side: The arm side this capture belongs to.
        open_rad: Native rad captured at the physical open stop.
        close_rad: Native rad captured at the physical close stop.
        open_captured: Whether `open_rad` came from a physical capture (vs a default).
        close_captured: As above for the close endpoint.
    """

    side: str
    open_rad: float
    close_rad: float
    open_captured: bool = False
    close_captured: bool = False

    def __post_init__(self) -> None:
        """Validate the side token; endpoint separation is checked by `require_mappable`."""
        self.side = _require_side(self.side)

    def require_mappable(self) -> None:
        """Refuse a degenerate capture whose endpoints coincide.

        Raises:
            GripperConfigError: If the two endpoints are closer than the minimum
                separation, which would make the norm map divide by ~0.
        """
        if abs(self.close_rad - self.open_rad) < MIN_ENDPOINT_SEPARATION_RAD:
            raise GripperConfigError(
                f"{self.side} gripper endpoints coincide "
                f"(open_rad={self.open_rad}, close_rad={self.close_rad}); norm map undefined"
            )

    @classmethod
    def from_calibration(cls, calibration: OpenArmCalibration) -> GripperEndpointCapture:
        """Build a capture from a per-arm calibration's gripper endpoints (CTR-CAL reuse).

        The per-arm zero calibration already persists the gripper open/close rads; this
        reads them rather than re-capturing, so the two never drift.

        Args:
            calibration: The follower arm's calibration record.

        Returns:
            (GripperEndpointCapture) The capture for that arm's side.
        """
        return cls(
            side=calibration.side,
            open_rad=calibration.gripper_open_rad,
            close_rad=calibration.gripper_close_rad,
            open_captured=calibration.gripper_open_captured,
            close_captured=calibration.gripper_close_captured,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-ready mapping for this capture."""
        return {
            "side": self.side,
            "open_rad": self.open_rad,
            "close_rad": self.close_rad,
            "open_captured": self.open_captured,
            "close_captured": self.close_captured,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], where: str) -> GripperEndpointCapture:
        """Rebuild a capture from a parsed mapping, refusing unknown fields.

        Args:
            data: A parsed capture mapping.
            where: The field name this capture sits under, for error messages.

        Returns:
            (GripperEndpointCapture) The rebuilt capture.

        Raises:
            GripperConfigError: On unknown or missing fields.
        """
        return cls(**_checked_kwargs(cls, data, where))


@dataclass
class GripperLimits:
    """One side's `(lo, hi)` gripper joint limits — the subject of the sign mirror.

    Attributes:
        side: The arm side these limits belong to.
        lo_rad: The lower limit endpoint, rad (as written, not sorted).
        hi_rad: The upper limit endpoint, rad (as written, not sorted).
    """

    side: str
    lo_rad: float
    hi_rad: float

    def __post_init__(self) -> None:
        """Validate the side token."""
        self.side = _require_side(self.side)

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-ready mapping for these limits."""
        return {"side": self.side, "lo_rad": self.lo_rad, "hi_rad": self.hi_rad}

    @classmethod
    def from_dict(cls, data: dict[str, Any], where: str) -> GripperLimits:
        """Rebuild limits from a parsed mapping, refusing unknown fields.

        Args:
            data: A parsed limits mapping.
            where: The field name these limits sit under, for error messages.

        Returns:
            (GripperLimits) The rebuilt limits.

        Raises:
            GripperConfigError: On unknown or missing fields.
        """
        return cls(**_checked_kwargs(cls, data, where))


def mirror_limits(right: GripperLimits) -> tuple[float, float]:
    """Return the sign-reflected left endpoints for a right pair: `(-hi_right, -lo_right)`.

    Args:
        right: The right side's limits.

    Returns:
        (tuple[float, float]) The `(lo, hi)` the left limits must equal (FR-MAN-017).
    """
    return (-right.hi_rad, -right.lo_rad)


@dataclass
class GripperMirrorRecord:
    """The persisted cross-arm gripper record with its sign-mirror invariant.

    Its invariant is the one a single-arm calibration cannot express:
    `left_limits == (-hi_right, -lo_right)` (FR-MAN-017, FR-TEL-059). Constructing a
    record whose left limits are not the sign mirror of the right raises, which is
    the load refusal — a left arm configured with the un-mirrored right limits would
    silently clip its open command to zero and never open.

    Attributes:
        right_capture: The right side's endpoint capture (norm-map anchors).
        left_capture: The left side's endpoint capture.
        right_limits: The right side's joint limits.
        left_limits: The left side's joint limits; must sign-mirror `right_limits`.
        speed_rad_s: The requested POS_FORCE speed cap; the effective value is this
            clamped to the DM4310 V_MAX (`effective_speed_rad_s`).
        torque_pu: The per-unit force cap, in [0, 1].
        schema_version: The record schema generation.
        created_at: ISO-8601 UTC stamp of first write, set by the persistence layer.
        last_updated_at: ISO-8601 UTC stamp of the latest write.
        checksum: sha256 hex over the canonical body excluding this field.
    """

    right_capture: GripperEndpointCapture
    left_capture: GripperEndpointCapture
    right_limits: GripperLimits
    left_limits: GripperLimits
    speed_rad_s: float
    torque_pu: float
    schema_version: int = SCHEMA_VERSION
    created_at: str | None = None
    last_updated_at: str | None = None
    checksum: str = ""

    def __post_init__(self) -> None:
        """Enforce every invariant the field types cannot: schema generation, side
        assignment, non-degenerate captures, per-unit force, and the sign mirror."""
        if self.schema_version != SCHEMA_VERSION:
            raise GripperConfigError(
                f"schema_version must be {SCHEMA_VERSION}, got {self.schema_version}"
            )
        if self.right_capture.side != SIDE_RIGHT or self.right_limits.side != SIDE_RIGHT:
            raise GripperConfigError("right_capture and right_limits must be side='right'")
        if self.left_capture.side != SIDE_LEFT or self.left_limits.side != SIDE_LEFT:
            raise GripperConfigError("left_capture and left_limits must be side='left'")
        self.right_capture.require_mappable()
        self.left_capture.require_mappable()
        # torque_pu and speed are validated by the POS_FORCE surface so there is one
        # rule for each, not a second copy here: force out of [0,1] refuses, speed
        # clamps at exposure.
        validate_torque_pu(self.torque_pu)
        clamp_speed_rad_s(self.speed_rad_s)
        self._require_sign_mirror()

    def _require_sign_mirror(self) -> None:
        """Refuse a config whose left limits are not the sign mirror of the right.

        Raises:
            GripperConfigError: If `left_limits != (-hi_right, -lo_right)` within
                tolerance (FR-MAN-017, FR-TEL-059).
        """
        want_lo, want_hi = mirror_limits(self.right_limits)
        if (
            abs(self.left_limits.lo_rad - want_lo) > MIRROR_TOLERANCE_RAD
            or abs(self.left_limits.hi_rad - want_hi) > MIRROR_TOLERANCE_RAD
        ):
            raise GripperConfigError(
                "left gripper limits must sign-mirror the right: expected "
                f"(lo={want_lo}, hi={want_hi}) = (-hi_right, -lo_right), got "
                f"(lo={self.left_limits.lo_rad}, hi={self.left_limits.hi_rad}); "
                "an un-mirrored left arm clips its open command to zero and never opens"
            )

    @property
    def effective_speed_rad_s(self) -> float:
        """The speed cap actually applied: the request clamped to the DM4310 V_MAX."""
        return clamp_speed_rad_s(self.speed_rad_s)

    def norm_map_for(self, side: str) -> GripperEndpointCapture:
        """Return the endpoint capture that defines a side's norm[0,1] map.

        Args:
            side: The arm side.

        Returns:
            (GripperEndpointCapture) That side's capture.

        Raises:
            GripperConfigError: If `side` is not `left` or `right`.
        """
        if _require_side(side) == SIDE_RIGHT:
            return self.right_capture
        return self.left_capture

    def canonical_body(self) -> dict[str, Any]:
        """Return the JSON-ready body with the checksum field removed.

        The checksum is computed over exactly this dict, so excluding `checksum` and
        sorting keys is what makes the value a function of content alone.

        Returns:
            (dict[str, Any]) The canonical body.
        """
        return {
            "right_capture": self.right_capture.to_dict(),
            "left_capture": self.left_capture.to_dict(),
            "right_limits": self.right_limits.to_dict(),
            "left_limits": self.left_limits.to_dict(),
            "speed_rad_s": self.speed_rad_s,
            "torque_pu": self.torque_pu,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "last_updated_at": self.last_updated_at,
        }

    def compute_checksum(self) -> str:
        """Return the sha256 hex of the canonical body (excludes the checksum field)."""
        payload = json.dumps(self.canonical_body(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_json_dict(self) -> dict[str, Any]:
        """Return the full JSON object (body plus a freshly computed checksum)."""
        body = self.canonical_body()
        body["checksum"] = self.compute_checksum()
        return body

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> GripperMirrorRecord:
        """Build and validate a record from a parsed JSON object.

        Args:
            data: A parsed record object.

        Returns:
            (GripperMirrorRecord) The validated record.

        Raises:
            GripperConfigError: On unknown or missing fields, a checksum mismatch, or
                any invariant violation (including the sign mirror), which is the load
                refusal of acceptance (2).
        """
        known = set(cls.__dataclass_fields__)
        unknown = set(data) - known
        if unknown:
            raise GripperConfigError(f"unknown gripper record field(s): {sorted(unknown)}")
        stored_checksum = str(data.get("checksum", ""))
        try:
            record = cls(
                right_capture=GripperEndpointCapture.from_dict(
                    data["right_capture"], "right_capture"
                ),
                left_capture=GripperEndpointCapture.from_dict(data["left_capture"], "left_capture"),
                right_limits=GripperLimits.from_dict(data["right_limits"], "right_limits"),
                left_limits=GripperLimits.from_dict(data["left_limits"], "left_limits"),
                speed_rad_s=float(data["speed_rad_s"]),
                torque_pu=float(data["torque_pu"]),
                schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
                created_at=data.get("created_at"),
                last_updated_at=data.get("last_updated_at"),
            )
        except KeyError as exc:
            raise GripperConfigError(f"gripper record missing required field: {exc}") from exc
        if stored_checksum and stored_checksum != record.compute_checksum():
            raise GripperConfigError(
                "gripper record checksum mismatch: the body does not hash to its recorded checksum"
            )
        record.checksum = stored_checksum or record.compute_checksum()
        return record


def _checked_kwargs(cls: type, data: dict[str, Any], where: str) -> dict[str, Any]:
    """Return `data` as constructor kwargs, refusing fields the dataclass does not declare.

    Args:
        cls: The target dataclass.
        data: A parsed mapping.
        where: The field name the mapping sits under, for error messages.

    Returns:
        (dict[str, Any]) The mapping, once confirmed to hold only known fields.

    Raises:
        GripperConfigError: On unknown fields or a non-mapping value.
    """
    if not isinstance(data, dict):
        raise GripperConfigError(f"{where} must be a mapping, got {type(data).__name__}")
    known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
    unknown = set(data) - known
    if unknown:
        raise GripperConfigError(f"unknown field(s) in {where}: {sorted(unknown)}")
    return dict(data)
