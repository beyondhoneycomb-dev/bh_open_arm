"""CTR-CAM@v1 consumes CTR-PRIM@v1 by reference and joins across the four surfaces.

`02b` §5.0b row 1: the camera identifier is one slot key that round-trips across
the CAM registry key, the CAP sidecar column, the WS frame tag and the REC image
key. This proves the camera schema uses the *same* `CTR-PRIM@v1` types — by object
identity, not a look-alike — and that a registered camera's slot joins all four.
"""

from __future__ import annotations

import contracts.camera_registry as cam
import contracts.prim as prim
from contracts.prim import (
    REGISTRY,
    CameraSlotKey,
    ErrorEnvelope,
    FrameType,
    codes,
    slot_from_capture_ts_column,
    slot_from_image_key,
    slot_from_ws_tag,
)


def test_capability_floor_is_the_prim_frame_type() -> None:
    """The required/optional split is stated over the CTR-PRIM frame-type enum itself."""
    assert prim.REQUIRED_FRAME_TYPE is FrameType.RGB
    assert {FrameType.RGB, FrameType.DEPTH} == cam.SUPPORTED_CAPABILITIES
    assert prim.OPTIONAL_FRAME_TYPES == (FrameType.DEPTH,)


def test_registered_slot_round_trips_across_cam_cap_ws_rec() -> None:
    """One registered camera's slot key joins CAM, CAP, WS and REC surfaces."""
    spec = cam.make_arm_camera("left", "wrist", frozenset({FrameType.RGB, FrameType.DEPTH}))
    slot = spec.slot

    image_key = spec.dataset_image_key()
    capture_column = f"{slot.value}_capture_ts"
    ws_tag = slot.ws_tag(FrameType.RGB)

    assert slot_from_image_key(image_key) == slot
    assert slot_from_capture_ts_column(capture_column) == slot
    assert slot_from_ws_tag(ws_tag) == slot
    assert isinstance(slot, CameraSlotKey)


def test_error_envelope_is_the_shared_prim_envelope() -> None:
    """A camera error is the CTR-PRIM envelope wrapping a registered OA-CAM code."""
    envelope = cam.camera_error(REGISTRY.get(codes.OA_CAM_001), "camera disconnected mid-session")
    assert isinstance(envelope, ErrorEnvelope)
    assert envelope.code == "OA-CAM-001"
    assert envelope.reason == "camera disconnected mid-session"


def test_dataset_depth_key_present_only_with_depth_capability() -> None:
    """The depth feature key is derived only for a depth-capable camera."""
    rgb_only = cam.make_top_level_camera("front", frozenset({FrameType.RGB}))
    with_depth = cam.make_top_level_camera("overhead", frozenset({FrameType.RGB, FrameType.DEPTH}))

    assert rgb_only.dataset_depth_key() is None
    assert with_depth.dataset_depth_key() == "observation.images.overhead_depth"
    assert slot_from_image_key(with_depth.dataset_image_key()) == with_depth.slot
