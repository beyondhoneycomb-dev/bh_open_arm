"""CTR-CAM@v1 consumption — budget a frozen `CameraSpec`, depth-on = two streams.

WP-3B-02's input is WP-3A-01 (CTR-CAM@v1). These exercise the budget over the frozen
camera model an operator actually configures: a depth-capable spec costs two streams,
and the arithmetic is the imported WP-0B-08 formula, not a second copy.
"""

from __future__ import annotations

import pytest

from backend.camera.bandwidth import profile_bandwidth_mbps
from backend.sensing.bandwidth.spec import (
    spec_bandwidth_mbps,
    spec_profiles,
    spec_stream_count,
    specs_total_mbps,
)
from contracts.camera_registry import CameraSpec
from contracts.prim import CameraSlotKey, FrameType


def _spec(slot: str, *, depth: bool) -> CameraSpec:
    """A configured 640×480@30 CameraSpec, RGB-only or RGB+depth."""
    capabilities = {FrameType.RGB}
    if depth:
        capabilities = {FrameType.RGB, FrameType.DEPTH}
    return CameraSpec(
        slot=CameraSlotKey(slot),
        capabilities=frozenset(capabilities),
        width=640,
        height=480,
        fps=30,
    )


def test_depth_capable_spec_is_two_streams() -> None:
    """has_depth makes the spec cost two streams (FR-CAM-010)."""
    assert spec_stream_count(_spec("wrist", depth=False)) == 1
    assert spec_stream_count(_spec("wrist", depth=True)) == 2
    assert len(spec_profiles(_spec("wrist", depth=True))) == 2


def test_depth_on_doubles_spec_bandwidth() -> None:
    """color+depth at one geometry is exactly twice color-only (z16 = YUYV width)."""
    rgb = spec_bandwidth_mbps(_spec("wrist", depth=False))
    rgbd = spec_bandwidth_mbps(_spec("wrist", depth=True))
    assert rgbd == pytest.approx(2 * rgb)


def test_spec_bandwidth_reuses_the_formula() -> None:
    """The spec total equals the imported per-profile formula summed over its streams."""
    spec = _spec("wrist", depth=True)
    expected = sum(profile_bandwidth_mbps(profile) for profile in spec_profiles(spec))
    assert spec_bandwidth_mbps(spec) == pytest.approx(expected)


def test_unconfigured_spec_has_no_budget() -> None:
    """An unconfigured spec cannot start collection, so it has no bandwidth to sum."""
    unconfigured = CameraSpec(
        slot=CameraSlotKey("wrist"),
        capabilities=frozenset({FrameType.RGB}),
        width=None,
        height=None,
        fps=None,
    )
    with pytest.raises(ValueError, match="not configured"):
        spec_bandwidth_mbps(unconfigured)


def test_registry_aggregate_sums_every_spec() -> None:
    """The aggregate is the sum over the registered specs, depth counted per camera."""
    specs = [_spec("wrist", depth=True), _spec("front", depth=False)]
    total = specs_total_mbps(specs)
    assert total == pytest.approx(sum(spec_bandwidth_mbps(spec) for spec in specs))
