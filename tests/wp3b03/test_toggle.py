"""WP-3B-03 acceptance ① — the per-camera use_depth toggle and (H, W, 1) depth shape.

Runs here on synthetic depth arrays (`02b` §6.2 WP-3B-03 ②③): depth is toggled per
camera, is intelrealsense-only, is never an implicit policy input, and the `{cam}_depth`
frame is validated against the `CTR-CAM@v1`/`CTR-PRIM@v1` `(H, W, 1)` uint16 shape.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.sensing.depth.toggle import (
    DepthShapeError,
    DepthToggleError,
    DepthToggles,
    depth_dataset_key,
    depth_feature_shape,
    resolve_depth_toggles,
    validate_depth_frame,
)
from contracts.camera_registry import CameraRegistry, CameraSpec
from contracts.fixtures.synthetic_camera import SyntheticCamera
from contracts.prim import CameraSlotKey, FrameType

_WIDTH = 8
_HEIGHT = 6
_FPS = 30


def _depth_camera(name: str) -> CameraSpec:
    """A configured RGB+depth camera."""
    return CameraSpec(
        slot=CameraSlotKey(name),
        capabilities=frozenset({FrameType.RGB, FrameType.DEPTH}),
        width=_WIDTH,
        height=_HEIGHT,
        fps=_FPS,
    )


def _rgb_camera(name: str) -> CameraSpec:
    """A configured RGB-only camera."""
    return CameraSpec(
        slot=CameraSlotKey(name),
        capabilities=frozenset({FrameType.RGB}),
        width=_WIDTH,
        height=_HEIGHT,
        fps=_FPS,
    )


def test_depth_feature_shape_and_key_derive_from_the_contract() -> None:
    """The depth shape is (H, W, 1) and the key is the registry's derivation."""
    spec = _depth_camera("overhead")
    assert depth_feature_shape(spec) == (_HEIGHT, _WIDTH, 1)
    assert depth_dataset_key(spec) == "observation.images.overhead_depth"


def test_toggle_enables_a_depth_camera_and_rejects_an_rgb_only_one() -> None:
    """use_depth is intelrealsense-only: enabling it on an RGB-only camera is refused."""
    registry = CameraRegistry()
    registry.register(_depth_camera("overhead"))
    registry.register(_rgb_camera("front"))

    toggles = resolve_depth_toggles(registry, [CameraSlotKey("overhead")])
    assert toggles.is_enabled(CameraSlotKey("overhead"))
    assert toggles.any_enabled

    with pytest.raises(DepthToggleError, match="no depth capability"):
        resolve_depth_toggles(registry, [CameraSlotKey("front")])


def test_depth_is_not_forced_default_is_rgb_only() -> None:
    """A depth-capable camera stays off until toggled — depth is never implicit (③)."""
    empty = DepthToggles(frozenset())
    assert not empty.any_enabled
    assert not empty.is_enabled(CameraSlotKey("overhead"))


def test_rgb_only_camera_has_no_depth_shape_or_key() -> None:
    """An RGB-only camera exposes neither a depth shape nor a depth key."""
    spec = _rgb_camera("front")
    with pytest.raises(DepthToggleError):
        depth_feature_shape(spec)
    with pytest.raises(DepthToggleError):
        depth_dataset_key(spec)


def test_unconfigured_camera_has_no_depth_shape() -> None:
    """Depth shape is undefined until width/height are configured (CTR-CAM@v1)."""
    spec = CameraSpec(
        slot=CameraSlotKey("overhead"),
        capabilities=frozenset({FrameType.RGB, FrameType.DEPTH}),
        width=None,
        height=None,
        fps=None,
    )
    with pytest.raises(DepthShapeError):
        depth_feature_shape(spec)


def test_validate_accepts_a_synthetic_fixture_depth_frame() -> None:
    """A depth frame from the 3A synthetic fixture passes the (H, W, 1) uint16 check."""
    spec = _depth_camera("overhead")
    camera = SyntheticCamera(spec=spec, frame_type=FrameType.DEPTH)
    frame = camera.read(0)
    assert frame is not None
    depth = np.frombuffer(frame.data, dtype=np.uint16).reshape(_HEIGHT, _WIDTH, 1)
    validate_depth_frame(spec, depth)


@pytest.mark.parametrize(
    "bad",
    [
        np.zeros((_HEIGHT, _WIDTH, 3), dtype=np.uint16),
        np.zeros((_HEIGHT, _WIDTH), dtype=np.uint16),
        np.zeros((_WIDTH, _HEIGHT, 1), dtype=np.uint16),
        np.zeros((_HEIGHT, _WIDTH, 1), dtype=np.uint8),
    ],
)
def test_validate_rejects_malformed_depth_frames(bad: np.ndarray) -> None:
    """A wrong channel count, missing axis, transposed geometry or dtype is rejected."""
    with pytest.raises(DepthShapeError):
        validate_depth_frame(_depth_camera("overhead"), bad)
