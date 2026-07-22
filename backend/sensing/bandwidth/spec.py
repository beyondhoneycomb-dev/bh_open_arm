"""Bandwidth of a frozen CTR-CAM@v1 camera, over the WP-0B-08 formula.

WP-3B-02's declared input is WP-3A-01 (CTR-CAM@v1): the camera set an operator
configures is the name-keyed `CameraSpec` registry, not a raw enumeration
descriptor. This module is that consumption — it turns a configured `CameraSpec`
into the streams the budget sums, reusing `profile_bandwidth_mbps` so the
`W×H×Bpp×8×fps` arithmetic stays single-sourced in `backend.camera.bandwidth`.
A depth-capable spec contributes two streams (color + depth) with no special case
(FR-CAM-010), because `has_depth` adds the second profile.

`bpp` is deliberately not a `CameraSpec` field: it belongs to the negotiated pixel
format, not to the camera (`06` §2.9). The budget is a worst-case pre-check, so it
defaults to the raw formats (YUYV color, z16 depth) and lets a caller pass a lower
color `bpp` once a compressed format is confirmed negotiated — the first rung of the
mitigation ladder.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.camera.bandwidth import profile_bandwidth_mbps
from backend.camera.constants import BPP_YUYV, BPP_Z16_DEPTH
from backend.camera.descriptor import CameraProfile, StreamKind
from contracts.camera_registry import CameraSpec


def spec_stream_count(spec: CameraSpec) -> int:
    """Return the number of streams a spec costs: 1 RGB-only, 2 with depth (FR-CAM-010)."""
    return 2 if spec.has_depth else 1


def spec_profiles(
    spec: CameraSpec,
    bpp_rgb: int = BPP_YUYV,
    bpp_depth: int = BPP_Z16_DEPTH,
) -> tuple[CameraProfile, ...]:
    """Build the WP-0B-08 profiles a configured `CameraSpec` streams.

    Args:
        spec: A configured CTR-CAM@v1 camera (width/height/fps set).
        bpp_rgb: Bytes-per-pixel of the negotiated color format.
        bpp_depth: Bytes-per-pixel of the depth format (z16 = 2).

    Returns:
        (tuple[CameraProfile, ...]) The color profile, plus depth when depth is on.

    Raises:
        ValueError: When the spec is not configured — an unconfigured camera cannot
            start collection (CTR-CAM@v1), so it has no budget to compute.
    """
    if not spec.is_configured:
        raise ValueError(
            f"camera {spec.slot.value!r} is not configured (width/height/fps); "
            "an unconfigured camera has no bandwidth to budget (CTR-CAM@v1)"
        )
    # is_configured guarantees these three are set; the asserts satisfy the checker.
    assert spec.width is not None and spec.height is not None and spec.fps is not None
    profiles = [CameraProfile(spec.width, spec.height, spec.fps, bpp_rgb, StreamKind.RGB)]
    if spec.has_depth:
        profiles.append(
            CameraProfile(spec.width, spec.height, spec.fps, bpp_depth, StreamKind.DEPTH)
        )
    return tuple(profiles)


def spec_bandwidth_mbps(
    spec: CameraSpec,
    bpp_rgb: int = BPP_YUYV,
    bpp_depth: int = BPP_Z16_DEPTH,
) -> float:
    """Return a configured spec's total bandwidth, color plus depth when depth is on.

    Args:
        spec: A configured CTR-CAM@v1 camera.
        bpp_rgb: Bytes-per-pixel of the negotiated color format.
        bpp_depth: Bytes-per-pixel of the depth format.

    Returns:
        (float) Total Mbps, summed over the spec's streams.
    """
    return sum(
        profile_bandwidth_mbps(profile) for profile in spec_profiles(spec, bpp_rgb, bpp_depth)
    )


def specs_total_mbps(
    specs: Sequence[CameraSpec],
    bpp_rgb: int = BPP_YUYV,
    bpp_depth: int = BPP_Z16_DEPTH,
) -> float:
    """Return the aggregate bandwidth of a registered set of CTR-CAM@v1 cameras.

    Args:
        specs: The configured cameras in the registry.
        bpp_rgb: Bytes-per-pixel of the negotiated color format.
        bpp_depth: Bytes-per-pixel of the depth format.

    Returns:
        (float) Aggregate Mbps over every spec's streams.
    """
    return sum(spec_bandwidth_mbps(spec, bpp_rgb, bpp_depth) for spec in specs)


__all__ = [
    "spec_bandwidth_mbps",
    "spec_profiles",
    "spec_stream_count",
    "specs_total_mbps",
]
