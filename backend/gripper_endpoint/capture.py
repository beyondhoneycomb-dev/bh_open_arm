"""Operator-assisted endpoint capture flow (FR-MAN-016) — physical read deferred.

On the robot the operator moves the gripper to each mechanical stop and the flow
records the motor's *current native rad*. That physical read needs the operator and a
live DM4310, and is the SHAPE-HG deferred stage of WP-2A-08. Offline, the flow is
exercised by injecting the rad, which proves the record-building, mirror-validation,
and persistence machinery runs without faking the hardware read — the machinery is
green here; only the physical bytes are pending, re-run by
`backend.gripper_endpoint.reverify`.
"""

from __future__ import annotations

from backend.gripper_endpoint.schema import (
    GripperEndpointCapture,
    GripperLimits,
    GripperMirrorRecord,
)


def build_capture(
    side: str,
    open_rad: float,
    close_rad: float,
    open_captured: bool,
    close_captured: bool,
) -> GripperEndpointCapture:
    """Build a validated endpoint capture from a side's two endpoint readings.

    On the robot `open_rad`/`close_rad` are the motor's native rad at the physical
    stops (the deferred read); offline they are injected. The result validates its
    side and non-degeneracy at build time.

    Args:
        side: The arm side being captured.
        open_rad: Native rad at the physical open stop.
        close_rad: Native rad at the physical close stop.
        open_captured: Whether the open reading came from a physical capture.
        close_captured: Whether the close reading came from a physical capture.

    Returns:
        (GripperEndpointCapture) The validated capture.
    """
    capture = GripperEndpointCapture(
        side=side,
        open_rad=open_rad,
        close_rad=close_rad,
        open_captured=open_captured,
        close_captured=close_captured,
    )
    capture.require_mappable()
    return capture


def build_mirror_record(
    right_capture: GripperEndpointCapture,
    left_capture: GripperEndpointCapture,
    right_limits: GripperLimits,
    left_limits: GripperLimits,
    speed_rad_s: float,
    torque_pu: float,
) -> GripperMirrorRecord:
    """Assemble a full cross-arm record, refusing it unless the sign mirror holds.

    The record's own construction enforces the sign mirror, the per-unit force domain,
    and the non-degenerate captures, so a bad pairing raises here rather than being
    written and refused later.

    Args:
        right_capture: The right side's endpoint capture.
        left_capture: The left side's endpoint capture.
        right_limits: The right side's joint limits.
        left_limits: The left side's joint limits.
        speed_rad_s: The requested POS_FORCE speed cap.
        torque_pu: The per-unit force cap.

    Returns:
        (GripperMirrorRecord) The validated cross-arm record.
    """
    return GripperMirrorRecord(
        right_capture=right_capture,
        left_capture=left_capture,
        right_limits=right_limits,
        left_limits=left_limits,
        speed_rad_s=speed_rad_s,
        torque_pu=torque_pu,
    )
