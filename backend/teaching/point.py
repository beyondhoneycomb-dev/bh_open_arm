"""The teaching-point record (WP-2D-05, 02b §4 산출).

A teaching point captures one taught arm posture together with the provenance a
replay needs to be safe: the zero reference it was taught against. The frozen field
set is ``{name, arm_side, q_urdf[8], ee_pose[7], gain_profile, zero_method,
zeroed_at, q_lift, timestamp}``.

The load-bearing invariant is that ``zero_method`` and ``zeroed_at`` are mandatory,
not decorative. A point that carries a joint vector but no record of the zero it was
taken against is un-replayable — the same ``q_urdf`` under a different zero reference
is a different physical pose — so the schema refuses to represent one (acceptance ①).
``zero_method`` reuses the calibration enum (``backend.calibration``) rather than
minting a second vocabulary for the same physical fact.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from backend.calibration.schema import ZeroMethod
from backend.teaching.constants import ARM_SIDES, EE_POSE_WIDTH, Q_URDF_WIDTH

_FIELDS = (
    "name",
    "arm_side",
    "q_urdf",
    "ee_pose",
    "gain_profile",
    "zero_method",
    "zeroed_at",
    "q_lift",
    "timestamp",
)


class TeachingPointError(ValueError):
    """Raised when a teaching-point payload violates the frozen WP-2D-05 shape."""


def _vector(name: str, values: list[float], width: int) -> list[float]:
    """Validate a fixed-width float vector and return it as a fresh list.

    Args:
        name: Field name, for the error message.
        values: The vector to check.
        width: Required length.

    Returns:
        (list[float]) The same values as a fresh list of floats.

    Raises:
        TeachingPointError: If the length is not ``width``.
    """
    if len(values) != width:
        raise TeachingPointError(f"{name} must have {width} entries, got {len(values)}")
    return [float(v) for v in values]


@dataclass(frozen=True)
class TeachingPoint:
    """One taught arm posture with the zero provenance a safe replay requires.

    Immutable: edits (rename, reorder, duplicate) produce a new instance via
    ``dataclasses.replace`` so a stored point can never be mutated out from under a
    replay verdict computed against it.

    Attributes:
        name: Human label, unique within one store.
        arm_side: "left" or "right"; the arm this posture belongs to.
        q_urdf: URDF-frame joint command, one value per motor (MOTOR_ORDER width).
        ee_pose: EE pose achieved when taught, float[7] = [px,py,pz,qw,qx,qy,qz].
        gain_profile: Name of the gain (kp/kd) profile the posture was taught under.
        zero_method: The zero reference the joint command is expressed against.
        zeroed_at: ISO-8601 timestamp of the set-zero event the posture depends on.
        q_lift: Lifter displacement (metres) at teach time; the base-frame reflection.
        timestamp: ISO-8601 creation time of this record.
    """

    name: str
    arm_side: str
    q_urdf: list[float]
    ee_pose: list[float]
    gain_profile: str
    zero_method: ZeroMethod
    zeroed_at: str
    q_lift: float
    timestamp: str

    def __post_init__(self) -> None:
        """Enforce the invariants the field types cannot: non-empty labels, the arm
        domain, vector widths, and the mandatory zero provenance (acceptance ①)."""
        if not self.name.strip():
            raise TeachingPointError("name must be a non-empty label")
        if self.arm_side not in ARM_SIDES:
            raise TeachingPointError(f"arm_side must be one of {ARM_SIDES}, got {self.arm_side!r}")
        if not self.gain_profile.strip():
            raise TeachingPointError("gain_profile must name a gain profile")
        # zeroed_at is what makes a point replayable; an empty one is the "lacking zero
        # provenance" case save must refuse, not a value to be filled in silently later.
        if not str(self.zeroed_at).strip():
            raise TeachingPointError(
                "zeroed_at is required — a point without its zero event is un-replayable"
            )
        object.__setattr__(self, "q_urdf", _vector("q_urdf", self.q_urdf, Q_URDF_WIDTH))
        object.__setattr__(self, "ee_pose", _vector("ee_pose", self.ee_pose, EE_POSE_WIDTH))
        object.__setattr__(self, "q_lift", float(self.q_lift))
        # A raw string (from JSON) coerces to the enum; an unknown method is refused
        # here rather than surfacing later as a mismatch the gate cannot interpret.
        try:
            object.__setattr__(self, "zero_method", ZeroMethod(self.zero_method))
        except ValueError as exc:
            raise TeachingPointError(f"zero_method is not a known zero reference: {exc}") from exc

    def renamed(self, new_name: str) -> TeachingPoint:
        """Return a copy under a new label (for duplicate/rename)."""
        return replace(self, name=new_name)

    def to_json_dict(self) -> dict[str, Any]:
        """Return the JSON-ready object with ``zero_method`` as its string value."""
        return {
            "name": self.name,
            "arm_side": self.arm_side,
            "q_urdf": list(self.q_urdf),
            "ee_pose": list(self.ee_pose),
            "gain_profile": self.gain_profile,
            "zero_method": self.zero_method.value,
            "zeroed_at": self.zeroed_at,
            "q_lift": self.q_lift,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> TeachingPoint:
        """Build a teaching point from a parsed JSON object, refusing a malformed one.

        A missing ``zero_method`` or ``zeroed_at`` is the acceptance-① refusal on the
        load side: a hand-edited file that dropped the zero provenance is rejected at
        read time rather than surfacing later as a posture replayed against the wrong
        zero.

        Args:
            data: A parsed teaching-point JSON object.

        Returns:
            (TeachingPoint) The validated point.

        Raises:
            TeachingPointError: On an unknown field, a missing required field, or any
                shape violation.
        """
        unknown = set(data) - set(_FIELDS)
        if unknown:
            raise TeachingPointError(f"unknown teaching-point field(s): {sorted(unknown)}")
        missing = [field_name for field_name in _FIELDS if field_name not in data]
        if missing:
            raise TeachingPointError(f"teaching point is missing required field(s): {missing}")
        return cls(
            name=str(data["name"]),
            arm_side=str(data["arm_side"]),
            q_urdf=list(data["q_urdf"]),
            ee_pose=list(data["ee_pose"]),
            gain_profile=str(data["gain_profile"]),
            zero_method=data["zero_method"],
            zeroed_at=str(data["zeroed_at"]),
            q_lift=data["q_lift"],
            timestamp=str(data["timestamp"]),
        )
