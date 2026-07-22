"""The frozen OpenArm follower calibration schema (CTR-CAL@v1, 02 FR-CON-064, 16 M-1).

This is the CONTRACT_FROZEN source of truth for the shape of the on-disk calibration
JSON. Freezing it (`oa-contracts freeze CTR-CAL@v1`) is the WP-1-02 -> WP-1-03 handover
condition (01 §6.2): the hold target a scheduler commands cannot be defined until the
zero contract exists, so the schema is locked before any consumer reads it.

What lives where, and why the split matters (16 M-1):

- The joint zero itself lives in motor non-volatile memory, written by the Damiao
  `0xFE` set-zero command. It is NOT representable as a disk offset, so this schema
  does not store it as one. `motor_zero_raw` is the raw position READBACK captured at
  set-zero time — a witness used only to re-verify residual drift after a power cycle
  (FR-CON-065), never an offset applied to a reading.
- `urdf_zero_offset` is the expected URDF-zero reference the residual is measured
  against. Dropping it would let joint limits and the collision checker silently agree
  in two different coordinate frames (06 §3.2), so it is required.
- `0xAA` flash-store is firmware-unreliable and is never trusted or emitted; nothing
  here depends on it.

The schema carries a `checksum` over its own canonical body so a corrupt file is
distinguishable from a merely stale one, and the atomic writer (`atomic_io`) is what
guarantees a reader sees either the whole old file or the whole new one, never a torn
write. Units are fixed per field and stated in the field docs: joint positions are
degrees (Damiao native, and `q_lerobot(deg) = degrees(q_URDF)` per 02 Q-10), gripper
endpoints are radians (16 D-5, no load cell — captured by hand).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum
from typing import Any

# The contract id this schema is the frozen body of. Consumers key freeze checks and
# staleness on this exact string, so it is named once here.
CONTRACT_ID = "CTR-CAL@v1"

# The frozen schema generation. A shape change is a new generation (`@v2`), never an
# in-place edit of this literal (06 §4.3).
SCHEMA_VERSION = 1

# One follower arm carries seven revolute joints plus the gripper: eight actuators, in
# this fixed order. Every per-motor vector in the calibration has exactly this length,
# and index i names MOTOR_ORDER[i] in every one of them.
MOTOR_ORDER = (
    "joint_1",
    "joint_2",
    "joint_3",
    "joint_4",
    "joint_5",
    "joint_6",
    "joint_7",
    "gripper",
)
MOTOR_COUNT = len(MOTOR_ORDER)

# The per-joint residual tolerance the set-zero readback must fall within, in degrees
# (02 FR-CON-065, default ±0.5°). A joint whose measured angle after 0xFE differs from
# its `urdf_zero_offset` by more than this is not zeroed and re-zeroing is required.
ZERO_RESIDUAL_TOLERANCE_DEG = 0.5

# The identity sign and unit scale a fresh calibration seeds each joint with. The sign
# is the operator-perception sign confirmed at bring-up; the scale is 1.0 because
# `q_lerobot(deg) = degrees(q_URDF)` holds without a hanging-pose `calibrate()` (Q-10).
DEFAULT_JOINT_SIGN = 1
DEFAULT_JOINT_SCALE = 1.0


class ZeroMethod(StrEnum):
    """How the mechanical zero reference was established (02 FR-CON-031/065).

    Recorded so a later residual re-verification knows what physical reference the
    stored `motor_zero_raw` was taken against — a hardstop bump and a jig do not
    produce interchangeable references.
    """

    LEROBOT_HANGING = "lerobot_hanging"
    HARDSTOP_BUMP = "hardstop_bump"
    MECHANICAL_JIG = "mechanical_jig"


class CalibrationError(ValueError):
    """Raised when a calibration payload violates the frozen CTR-CAL@v1 shape."""


def _vector8(name: str, values: list[float]) -> list[float]:
    """Validate that a per-motor vector has exactly MOTOR_COUNT entries.

    Args:
        name: Field name, for the error message.
        values: The vector to check.

    Returns:
        (list[float]) The same values as a fresh list.

    Raises:
        CalibrationError: If the length is not MOTOR_COUNT.
    """
    if len(values) != MOTOR_COUNT:
        raise CalibrationError(
            f"{name} must have {MOTOR_COUNT} entries (one per motor {MOTOR_ORDER}), "
            f"got {len(values)}"
        )
    return [float(v) for v in values]


@dataclass
class OpenArmCalibration:
    """The on-disk calibration of one OpenArm follower arm (CTR-CAL@v1).

    Every per-motor list is indexed by `MOTOR_ORDER`. The joint zero is NOT here — it
    lives in motor NV (16 M-1); `motor_zero_raw` is the readback witness for residual
    re-verification, and `urdf_zero_offset` is the reference it is compared against.

    Attributes:
        robot_type: The follower plugin type this calibration belongs to.
        robot_id: The follower instance id (LeRobot `config.id`).
        side: Which arm ("left" or "right").
        motor_zero_raw: Raw joint position (degrees) read back immediately after the
            0xFE set-zero, per motor. A witness for power-cycle residual re-verify.
        joint_signs: Operator-perception sign (+1 or -1) per motor.
        joint_scale: Degrees-per-unit scale per motor (1.0 unless a motor deviates).
        urdf_zero_offset: Expected URDF-zero joint angle (degrees) per motor; the
            reference the residual is measured against.
        gripper_open_rad: Gripper fully-open endpoint (radians, 16 D-5).
        gripper_close_rad: Gripper fully-closed endpoint (radians, 16 D-5).
        gripper_open_captured: Whether `gripper_open_rad` was captured from hardware
            (True) or is a seeded default (False).
        gripper_close_captured: As above for the close endpoint.
        zero_method: How the mechanical zero reference was established.
        zero_residual_deg: Per-motor residual (degrees) measured at set-zero time, or
            None when zeroing has not yet run (hardware-measured, 02 FR-CON-065 ②).
        zero_power_cycle_verified: Whether 0xFE zero persistence across a power cycle
            was confirmed within tolerance (02 FR-CON-065 ③). False until measured.
        require_rezero_each_session: Whether every power session must explicitly
            re-zero. Conservative default True: the persistence of the 0xFE zero is
            unconfirmed until `zero_power_cycle_verified`, and forcing re-zero is the
            safe reading of an unmeasured invariant.
        created_at: ISO-8601 UTC timestamp of first creation, or None.
        last_updated_at: ISO-8601 UTC timestamp of the last write, or None.
        last_zero_at: ISO-8601 UTC timestamp of the last successful set-zero, or None.
        schema_version: The frozen generation (always SCHEMA_VERSION for @v1).
        checksum: sha256 hex over the canonical body excluding this field; "" until
            the writer stamps it.
    """

    robot_type: str
    robot_id: str
    side: str
    motor_zero_raw: list[float]
    urdf_zero_offset: list[float]
    gripper_open_rad: float
    gripper_close_rad: float
    joint_signs: list[int] = field(default_factory=lambda: [DEFAULT_JOINT_SIGN] * MOTOR_COUNT)
    joint_scale: list[float] = field(default_factory=lambda: [DEFAULT_JOINT_SCALE] * MOTOR_COUNT)
    gripper_open_captured: bool = False
    gripper_close_captured: bool = False
    zero_method: ZeroMethod = ZeroMethod.LEROBOT_HANGING
    zero_residual_deg: list[float] | None = None
    zero_power_cycle_verified: bool = False
    require_rezero_each_session: bool = True
    created_at: str | None = None
    last_updated_at: str | None = None
    last_zero_at: str | None = None
    schema_version: int = SCHEMA_VERSION
    checksum: str = ""

    def __post_init__(self) -> None:
        """Enforce the frozen invariants the field types cannot: vector widths, sign
        domain, side domain, and the schema generation."""
        if self.schema_version != SCHEMA_VERSION:
            raise CalibrationError(
                f"schema_version must be {SCHEMA_VERSION} for {CONTRACT_ID}, "
                f"got {self.schema_version}"
            )
        if self.side not in ("left", "right"):
            raise CalibrationError(f"side must be 'left' or 'right', got {self.side!r}")
        self.motor_zero_raw = _vector8("motor_zero_raw", self.motor_zero_raw)
        self.urdf_zero_offset = _vector8("urdf_zero_offset", self.urdf_zero_offset)
        self.joint_scale = _vector8("joint_scale", self.joint_scale)
        signs = _vector8("joint_signs", [float(s) for s in self.joint_signs])
        if any(s not in (-1.0, 1.0) for s in signs):
            raise CalibrationError(
                f"joint_signs entries must each be +1 or -1, got {self.joint_signs}"
            )
        self.joint_signs = [int(s) for s in signs]
        if self.zero_residual_deg is not None:
            self.zero_residual_deg = _vector8("zero_residual_deg", self.zero_residual_deg)
        # from_json_dict passes zero_method as its raw string; coercion is idempotent on
        # an existing member, so it runs unconditionally rather than behind a type guard.
        self.zero_method = ZeroMethod(self.zero_method)

    def canonical_body(self) -> dict[str, Any]:
        """Return the JSON-ready body with the checksum field removed.

        The checksum is computed over exactly this dict, so it must be reproduced
        byte-for-byte on both sides; sorting keys and excluding `checksum` is what
        makes the value a function of content alone.

        Returns:
            (dict[str, Any]) The canonical body, `zero_method` as its string value.
        """
        body = asdict(self)
        body["zero_method"] = self.zero_method.value
        body.pop("checksum", None)
        return body

    def compute_checksum(self) -> str:
        """Return the sha256 hex of the canonical body (excludes the checksum field)."""
        payload = json.dumps(self.canonical_body(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def with_checksum(self) -> OpenArmCalibration:
        """Return a copy whose `checksum` is the freshly computed digest of its body."""
        return replace(self, checksum=self.compute_checksum())

    def to_json_dict(self) -> dict[str, Any]:
        """Return the full JSON object (body plus a freshly computed checksum)."""
        body = self.canonical_body()
        body["checksum"] = self.compute_checksum()
        return body

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> OpenArmCalibration:
        """Build a calibration from a parsed JSON object, validating the checksum.

        Args:
            data: A parsed calibration JSON object.

        Returns:
            (OpenArmCalibration) The validated calibration.

        Raises:
            CalibrationError: If the payload is missing a required field, has an
                extra field, or carries a checksum that does not match its body.
        """
        known = set(cls.__dataclass_fields__)
        unknown = set(data) - known
        if unknown:
            raise CalibrationError(f"unknown calibration field(s): {sorted(unknown)}")
        stored_checksum = data.get("checksum", "")
        kwargs = {k: v for k, v in data.items() if k != "checksum"}
        try:
            calibration = cls(**kwargs)
        except TypeError as exc:
            raise CalibrationError(
                f"calibration payload does not match {CONTRACT_ID}: {exc}"
            ) from exc
        if stored_checksum and stored_checksum != calibration.compute_checksum():
            raise CalibrationError(
                "calibration checksum mismatch: the body does not hash to its recorded checksum"
            )
        return replace(calibration, checksum=stored_checksum or calibration.compute_checksum())
