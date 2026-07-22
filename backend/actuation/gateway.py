"""Turning a position target into the MIT batch the CAN writer sends.

This is where CTR-UNIT and CTR-ACT meet the wire. A producer's request is a
`RequestedPositionAction` in **degrees**; the joint bus speaks **radians**
(`01` FR-SYS-016). The crossing happens here and only here, through the one
sanctioned `deg_to_rad` conversion — this is the "CAN ↔ gateway" boundary the
CTR-UNIT boundary table declares, kept to a single site so no second, unchecked
degree-to-radian path can appear (`02a` §3.2 WP-0A-04 ⑤).

The gateway is intentionally thin. It clamps a request to a symmetric joint limit
when one is supplied and records why (a `SafetyOverride` for the audit), but it
bakes in no safety thresholds of its own — the limits are passed in, because the
values belong to the gateway/calibration owners, not to the scheduler. A position
command and a position hold are the same shape (`ExecutedMitCommand` per joint,
zero feed-forward velocity and torque); they differ only in the target angle.
"""

from __future__ import annotations

from backend.actuation.config import HOLD_TORQUE, HOLD_VELOCITY, MIT_HOLD_KD, MIT_HOLD_KP
from contracts.action import (
    AcceptedPositionAction,
    ClampReason,
    ExecutedMitCommand,
    RequestedPositionAction,
    SafetyOverride,
)
from contracts.units import Deg, Nm, Rad, deg_to_rad

# Symmetric per-joint position bound, in degrees: (low, high) inclusive. A limit of
# None on a joint means "no clamp on this joint" (pass-through), used by the
# AI-offline harness, which is not the owner of any real joint envelope.
JointLimit = tuple[Deg, Deg]


def clamp_request(
    request: RequestedPositionAction,
    limits: tuple[JointLimit | None, ...] | None,
) -> tuple[AcceptedPositionAction, SafetyOverride]:
    """Clamp a position request to per-joint limits, recording whether it moved.

    Args:
        request: The producer's pre-clamp position request, in degrees.
        limits: One optional `(low, high)` degree bound per joint, or None to clamp
            no joint. Length, when given, must match the request width.

    Returns:
        (tuple[AcceptedPositionAction, SafetyOverride]) The clamped action and an
        audit record stating whether a joint limit altered the request.

    Raises:
        ValueError: If `limits` is given but does not match the request width.
    """
    if limits is None:
        accepted = AcceptedPositionAction(values=request.values)
        override = SafetyOverride(
            override_active=False, clamp_reason=ClampReason.NONE, stale=False, latched=False
        )
        return accepted, override

    if len(limits) != len(request.values):
        raise ValueError(
            f"limits width {len(limits)} does not match request width {len(request.values)}"
        )

    clamped: list[Deg] = []
    hit_limit = False
    for angle, limit in zip(request.values, limits, strict=True):
        if limit is None:
            clamped.append(angle)
            continue
        low, high = limit
        bounded = min(max(angle, low), high)
        if bounded != angle:
            hit_limit = True
        clamped.append(bounded)

    accepted = AcceptedPositionAction(values=tuple(clamped))
    override = SafetyOverride(
        override_active=hit_limit,
        clamp_reason=ClampReason.JOINT_LIMIT if hit_limit else ClampReason.NONE,
        stale=False,
        latched=False,
    )
    return accepted, override


def accepted_to_rad(accepted: AcceptedPositionAction) -> tuple[Rad, ...]:
    """Convert an accepted degree action to per-joint radians (the CAN boundary).

    Args:
        accepted: The clamped, position-only action, in degrees.

    Returns:
        (tuple[Rad, ...]) The same angles in radians, one per joint.
    """
    return tuple(deg_to_rad(angle) for angle in accepted.values)


def positions_to_batch(
    positions: tuple[Rad, ...],
    feedforward_torque: tuple[Nm, ...] | None = None,
) -> tuple[ExecutedMitCommand, ...]:
    """Build a MIT batch that commands a set of joint positions and holds there.

    A command is position-only by default: zero feed-forward velocity and torque,
    fixed hold gains, so a hold frame and a fresh position command are produced by
    the same call and differ only in the positions passed. When a feed-forward
    torque is supplied — the gateway routing a compliant/reactive command past the
    old `send_action` tau=0 hardcode (`12` §2.7.0, `WP-1-03`) — it rides in the
    `tau` field; the scheduler strips it back to zero when it caches the frame as a
    hold, because a hold is always position-only (`02a` §3.1 ⑤).

    Args:
        positions: One target angle per joint, in radians.
        feedforward_torque: Optional per-joint feed-forward torque; None (the
            default) is a position-only command with zero feed-forward torque.

    Returns:
        (tuple[ExecutedMitCommand, ...]) One MIT command per joint.

    Raises:
        ValueError: If a feed-forward torque is given whose width differs from the
            position count.
    """
    if feedforward_torque is not None and len(feedforward_torque) != len(positions):
        raise ValueError(
            f"feed-forward torque width {len(feedforward_torque)} does not match position "
            f"count {len(positions)}"
        )
    torques = (
        feedforward_torque
        if feedforward_torque is not None
        else tuple(HOLD_TORQUE for _ in positions)
    )
    return tuple(
        ExecutedMitCommand(
            kp=MIT_HOLD_KP,
            kd=MIT_HOLD_KD,
            q=position,
            dq=HOLD_VELOCITY,
            tau=torque,
        )
        for position, torque in zip(positions, torques, strict=True)
    )
