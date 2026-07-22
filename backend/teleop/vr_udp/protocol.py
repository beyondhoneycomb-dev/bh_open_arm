"""Parse newline-terminated UTF-8 JSON datagrams into `VrFrame`s.

This is the RUNS-HERE parse path: the frozen synthetic stream serialised to the
wire keyset (`contracts/fixtures/vr_pose_stream.py`) is decoded here into per-arm
poses, three-level validity and both timestamps. Parsing is pure — the caller
supplies the PC receive instant it stamped when the datagram arrived — so the same
function serves the socket thread and a direct-bytes test with no socket.

A malformed datagram (not JSON, missing a required key, a non-finite number, a
validity outside 0/1/2) raises `FrameParseError`; the receive loop drops it and
counts it rather than letting one bad packet kill the stream. Pose-sanity beyond
finiteness (the `det ~ 0` singular-frame discard) is the WP-3B-10 safety gate.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from backend.teleop.vr_udp.constants import (
    ARM_GRIP_KEY,
    ARM_POSITION_KEY,
    ARM_QUATERNION_KEY,
    ARM_SIDES,
    ARM_VALIDITY_KEY,
    BUTTON_KEYS,
    FRAME_APPLIED,
    FRAME_DELIMITER,
    KEY_REFERENCE_POSE,
    KEY_SOURCE_TS,
    KEY_VALIDITY,
    TEXT_ENCODING,
)
from backend.teleop.vr_udp.frame import ArmPose, VrFrame
from backend.teleop.vr_udp.geometry import Vec3, is_finite_vec
from backend.teleop.vr_udp.transform import transform_controller_pose
from contracts.teleop import TeleopSample, TeleopValidity


class FrameParseError(ValueError):
    """Raised when a datagram is not a well-formed VR pose frame."""


def split_frames(data: bytes) -> list[bytes]:
    """Split a datagram into its newline-terminated frames, dropping empties.

    Args:
        data: Raw datagram bytes.

    Returns:
        (list[bytes]) The non-empty frame segments.
    """
    return [segment for segment in data.split(FRAME_DELIMITER) if segment.strip()]


def _require_floats(value: object, count: int, field: str) -> tuple[float, ...]:
    """Coerce a JSON value into a fixed-length tuple of finite floats.

    Args:
        value: The JSON value for the field.
        count: The exact number of components required.
        field: The wire key, for the error message.

    Returns:
        (tuple[float, ...]) The finite float components.

    Raises:
        FrameParseError: If the value is not `count` finite numbers.
    """
    if not isinstance(value, (list, tuple)) or len(value) != count:
        raise FrameParseError(f"field {field!r} must be {count} numbers, got {value!r}")
    try:
        floats = tuple(float(component) for component in value)
    except (TypeError, ValueError) as exc:
        raise FrameParseError(f"field {field!r} has a non-numeric component: {value!r}") from exc
    if not is_finite_vec(floats):
        raise FrameParseError(f"field {field!r} has a non-finite component: {value!r}")
    return floats


def _validity(value: object, field: str) -> TeleopValidity:
    """Coerce a JSON value into a three-level tracking validity.

    Args:
        value: The JSON value for the validity field.
        field: The wire key, for the error message.

    Returns:
        (TeleopValidity) OK, STALE or INVALID.

    Raises:
        FrameParseError: If the value is not one of 0/1/2.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise FrameParseError(f"validity {field!r} must be an int in 0/1/2, got {value!r}")
    try:
        return TeleopValidity(value)
    except ValueError as exc:
        raise FrameParseError(f"validity {field!r} outside 0/1/2: {value!r}") from exc


def _grip(value: object) -> float:
    """Coerce an optional grip value to a float, defaulting to 0.0 when absent."""
    if value is None:
        return 0.0
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise FrameParseError(f"grip must be a number, got {value!r}") from exc


def _reference(payload: Mapping[str, object]) -> Vec3 | None:
    """Return the optional NECK reference position, or None when absent."""
    if KEY_REFERENCE_POSE not in payload:
        return None
    reference = _require_floats(payload[KEY_REFERENCE_POSE], 3, KEY_REFERENCE_POSE)
    return (reference[0], reference[1], reference[2])


def _arm_pose(side: str, payload: Mapping[str, object], reference: Vec3 | None) -> ArmPose:
    """Decode one arm: its validity, transformed pose (if publishable) and grip.

    Args:
        side: `"left"` or `"right"`.
        payload: The decoded JSON object.
        reference: The optional NECK reference position for the frame.

    Returns:
        (ArmPose) The arm's decoded state; `world_pose` is None when INVALID.
    """
    validity = _validity(_get(payload, ARM_VALIDITY_KEY[side]), ARM_VALIDITY_KEY[side])
    position = _require_floats(_get(payload, ARM_POSITION_KEY[side]), 3, ARM_POSITION_KEY[side])
    quaternion = _require_floats(
        _get(payload, ARM_QUATERNION_KEY[side]), 4, ARM_QUATERNION_KEY[side]
    )
    grip = _grip(payload.get(ARM_GRIP_KEY[side]))

    world_pose = None
    if validity.is_publishable:
        world_pose = transform_controller_pose(
            (position[0], position[1], position[2]),
            (quaternion[0], quaternion[1], quaternion[2], quaternion[3]),
            reference,
        )
    return ArmPose(side=side, validity=validity, world_pose=world_pose, grip=grip)


def _get(payload: Mapping[str, object], key: str) -> object:
    """Return a required field, raising `FrameParseError` when it is absent."""
    if key not in payload:
        raise FrameParseError(f"missing required field {key!r}")
    return payload[key]


def parse_datagram(frame: bytes, receive_mono_ns: int) -> VrFrame:
    """Parse one newline-terminated UTF-8 JSON frame into a `VrFrame`.

    Args:
        frame: One frame's bytes (without or with a trailing newline).
        receive_mono_ns: The PC receive instant the caller stamped on arrival
            (SERVER `CLOCK_MONOTONIC` nanoseconds), preserved alongside the source
            `t` — the two are never collapsed into one timestamp.

    Returns:
        (VrFrame) The parsed, transformed, dual-timestamped frame.

    Raises:
        FrameParseError: If the bytes are not a well-formed VR pose frame.
    """
    try:
        text = frame.decode(TEXT_ENCODING)
    except UnicodeDecodeError as exc:
        raise FrameParseError("datagram is not valid UTF-8") from exc
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FrameParseError(f"datagram is not valid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise FrameParseError(f"datagram is not a JSON object: {decoded!r}")
    payload: Mapping[str, object] = decoded

    source_ts_raw = _get(payload, KEY_SOURCE_TS)
    if isinstance(source_ts_raw, bool) or not isinstance(source_ts_raw, (int, float)):
        raise FrameParseError(f"source timestamp {KEY_SOURCE_TS!r} must be a number")
    source_ts = float(source_ts_raw)

    overall_validity = _validity(_get(payload, KEY_VALIDITY), KEY_VALIDITY)
    reference = _reference(payload)
    arms = {side: _arm_pose(side, payload, reference) for side in ARM_SIDES}
    buttons = {key: bool(payload.get(key, False)) for key in BUTTON_KEYS}

    teleop_sample = TeleopSample(
        source_ts=source_ts,
        receive_mono_ns=receive_mono_ns,
        validity=overall_validity,
    )
    return VrFrame(
        teleop_sample=teleop_sample,
        arms=arms,
        buttons=buttons,
        frame_applied=FRAME_APPLIED,
    )
