"""The zero-match replay gate (WP-2D-05 contract, 02b §4.2 ①②).

The contract this module enforces: a teaching point depends on the zero record it
was taught against, and a replay is permitted only when the robot's *current* zero
record is the same one. The hazard it exists to stop is silent replay after a zero
procedure change — the negative branch of 02b §4.2: the same ``q_urdf`` under a new
zero reference is a different physical pose, so replaying it drives the arm somewhere
the operator never taught (FR-MAN-008/039/040).

The identity is ``(side, zero_method, zeroed_at)``. A change to the method (a jig
swapped for a hardstop bump) or to the event timestamp (a re-zero, even by the same
method) both move the reference, so either mismatch blocks. A robot that has never
been zeroed (``last_zero_at`` is None) has no reference to match, so every replay is
blocked rather than run against an undefined zero.

``ZeroIdentity`` is derived from ``backend.calibration.OpenArmCalibration`` — the
frozen zero record — rather than a second copy of that state, so the gate and the
persisted zero can never disagree about what the current reference is.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from backend.calibration.schema import OpenArmCalibration, ZeroMethod
from backend.teaching.point import TeachingPoint


class ReplayDecision(Enum):
    """Whether a taught posture may be replayed against the current zero record."""

    ALLOWED = "allowed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ZeroIdentity:
    """The identity of one arm's current zero reference.

    Attributes:
        side: "left" or "right"; the arm this reference belongs to.
        zero_method: How the reference was established.
        zeroed_at: ISO-8601 timestamp of the set-zero event, or None when the arm has
            never been zeroed (no reference exists, so nothing may replay against it).
    """

    side: str
    zero_method: ZeroMethod
    zeroed_at: str | None

    @classmethod
    def from_calibration(cls, calibration: OpenArmCalibration) -> ZeroIdentity:
        """Derive the current zero identity from the frozen per-arm zero record.

        ``last_zero_at`` is the set-zero event the record last witnessed; it is the
        ``zeroed_at`` a point captured now would carry, so it is exactly what a later
        replay must still match.

        Args:
            calibration: The current per-arm calibration.

        Returns:
            (ZeroIdentity) The reference identity a replay is checked against.
        """
        return cls(
            side=calibration.side,
            zero_method=calibration.zero_method,
            zeroed_at=calibration.last_zero_at,
        )


@dataclass(frozen=True)
class ReplayVerdict:
    """The result of gating one teaching point against a current zero identity.

    Attributes:
        point_name: The gated point's label.
        decision: ALLOWED or BLOCKED.
        reason: The operator-facing warning when BLOCKED; empty when ALLOWED.
    """

    point_name: str
    decision: ReplayDecision
    reason: str

    @property
    def allowed(self) -> bool:
        """Whether the point may be replayed."""
        return self.decision is ReplayDecision.ALLOWED


def evaluate_replay(point: TeachingPoint, current: ZeroIdentity) -> ReplayVerdict:
    """Decide whether one taught posture may replay against the current zero record.

    This is the single gate: a posture is replayable only when the current reference
    is the very one it was taught against. Any of a cross-arm reference, an un-zeroed
    robot, a changed method, or a re-zero event blocks it, with a reason a UI shows as
    the acceptance-② warning.

    Args:
        point: The taught posture.
        current: The robot's current zero identity for the same arm.

    Returns:
        (ReplayVerdict) ALLOWED only on an exact identity match; else BLOCKED with a
        reason naming what diverged.
    """
    if point.arm_side != current.side:
        return _blocked(
            point,
            f"point is for the {point.arm_side} arm but the current zero record is {current.side}",
        )
    if not current.zeroed_at:
        return _blocked(
            point,
            "the robot has no zero record — set-zero the arm before replaying taught points",
        )
    if point.zero_method != current.zero_method:
        return _blocked(
            point,
            f"zero method changed since teaching ({point.zero_method.value} → "
            f"{current.zero_method.value}); the same joint angles are now a different pose",
        )
    if point.zeroed_at != current.zeroed_at:
        return _blocked(
            point,
            f"the arm was re-zeroed since teaching (taught at {point.zeroed_at}, current "
            f"zero {current.zeroed_at}); the same joint angles are now a different pose",
        )
    return ReplayVerdict(point_name=point.name, decision=ReplayDecision.ALLOWED, reason="")


def _blocked(point: TeachingPoint, reason: str) -> ReplayVerdict:
    """Build a BLOCKED verdict carrying the operator-facing warning."""
    return ReplayVerdict(point_name=point.name, decision=ReplayDecision.BLOCKED, reason=reason)


def capture_teaching_point(
    name: str,
    arm_side: str,
    q_urdf: list[float],
    ee_pose: list[float],
    gain_profile: str,
    q_lift: float,
    zero: ZeroIdentity,
) -> TeachingPoint:
    """Build a teaching point stamped with the current zero provenance.

    The sanctioned way to create a point: the zero method and event are taken from the
    live reference, so a point captured through here structurally cannot be missing the
    provenance acceptance ① requires. The arm side must match the reference the posture
    is being taught against.

    Args:
        name: Label for the new point.
        arm_side: The arm being taught; must equal ``zero.side``.
        q_urdf: URDF-frame joint command captured now.
        ee_pose: EE pose achieved now (float[7]).
        gain_profile: Gain profile in effect.
        q_lift: Lifter displacement now (metres).
        zero: The current zero identity the posture is taught against.

    Returns:
        (TeachingPoint) A point carrying the current zero provenance.

    Raises:
        ValueError: If ``arm_side`` disagrees with the zero reference, or the reference
            names no set-zero event to depend on.
    """
    if arm_side != zero.side:
        raise ValueError(f"cannot teach a {arm_side} point against the {zero.side} zero record")
    if not zero.zeroed_at:
        raise ValueError("cannot capture a point against an un-zeroed arm")
    return TeachingPoint(
        name=name,
        arm_side=arm_side,
        q_urdf=list(q_urdf),
        ee_pose=list(ee_pose),
        gain_profile=gain_profile,
        zero_method=zero.zero_method,
        zeroed_at=zero.zeroed_at,
        q_lift=float(q_lift),
        timestamp=datetime.now(UTC).isoformat(),
    )
