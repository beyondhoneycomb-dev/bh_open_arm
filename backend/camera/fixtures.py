"""Synthetic camera-descriptor fixtures — the corpus the calculators run against here.

These are hand-built descriptors and capture streams with *known* answers, so the
tests assert against arithmetic the specification itself states (`06` §2.9's 147.5 /
295 / 663 / 3539 / 882 Mbps figures) rather than against opaque magic. They stand in
for real enumeration on a host with no cameras, and share the exact shape a real
capture would carry — which is why `reverify` can consume either.

Nothing here is a numeric *target*: the bandwidth quads reproduce the spec's worked
examples to verify the formula and the block comparison, not to pin a pass line
(`02a` WP-0B-08 ⑨ — the `PG-CAM-001` cut is decided on real cameras).
"""

from __future__ import annotations

from backend.camera.constants import (
    BPP_RGB888,
    BPP_YUYV,
    BPP_Z16_DEPTH,
    NANOSECONDS_PER_MILLISECOND,
)
from backend.camera.descriptor import (
    CameraDescriptor,
    CameraProfile,
    CameraType,
    LinkSpeed,
    StreamKind,
)

# `06` §2.9: 640×480 YUYV @30 = 147.5 Mbps.
YUYV_640_480_30 = CameraProfile(640, 480, 30, BPP_YUYV, StreamKind.RGB)
# `06` §2.9: z16 depth pairs with the color stream at the same profile.
DEPTH_640_480_30 = CameraProfile(640, 480, 30, BPP_Z16_DEPTH, StreamKind.DEPTH)
# `06` §2.9: 1280×720 RGB888 @30 = 663 Mbps (the "> 660 Mbps" figure needs Bpp=3).
RGB888_1280_720_30 = CameraProfile(1280, 720, 30, BPP_RGB888, StreamKind.RGB)


def realsense_rgbd() -> CameraDescriptor:
    """A RealSense streaming color + depth at 640×480@30 (`06` §2.9: 295 Mbps)."""
    return CameraDescriptor(
        serial="rs-0001",
        camera_type=CameraType.INTEL_REALSENSE,
        model="Intel RealSense D435",
        profiles=(YUYV_640_480_30, DEPTH_640_480_30),
        controller="usb-controller-0",
        link_speed=LinkSpeed.USB3,
    )


def webcam_720p() -> CameraDescriptor:
    """A UVC webcam streaming 1280×720 RGB888@30 (`06` §2.9: 663 Mbps)."""
    return CameraDescriptor(
        serial="uvc-logitech-720",
        camera_type=CameraType.OPENCV,
        model="Logitech C920",
        profiles=(RGB888_1280_720_30,),
        controller="usb-controller-1",
        link_speed=LinkSpeed.USB3,
    )


def usb2_fallback_webcam() -> CameraDescriptor:
    """A webcam that negotiated a USB2 link — the FR-CAM-003 fallback case."""
    return CameraDescriptor(
        serial="uvc-fallback-480",
        camera_type=CameraType.OPENCV,
        model="Generic UVC",
        profiles=(YUYV_640_480_30,),
        controller="usb-controller-2",
        link_speed=LinkSpeed.USB2,
    )


def same_controller_pair() -> tuple[CameraDescriptor, CameraDescriptor]:
    """Two cameras on one controller — the FR-CAM-005 shared-controller warning case."""
    first = CameraDescriptor(
        serial="rs-share-a",
        camera_type=CameraType.INTEL_REALSENSE,
        model="Intel RealSense D435",
        profiles=(YUYV_640_480_30,),
        controller="usb-controller-shared",
        link_speed=LinkSpeed.USB3,
    )
    second = CameraDescriptor(
        serial="rs-share-b",
        camera_type=CameraType.INTEL_REALSENSE,
        model="Intel RealSense D435",
        profiles=(YUYV_640_480_30,),
        controller="usb-controller-shared",
        link_speed=LinkSpeed.USB3,
    )
    return first, second


def _d415_at(width: int, height: int, controller: str, index: int) -> CameraDescriptor:
    """A D415 streaming color + depth at one profile, both z16-width Bpp (§2.9)."""
    return CameraDescriptor(
        serial=f"d415-{index}",
        camera_type=CameraType.INTEL_REALSENSE,
        model="Intel RealSense D415",
        profiles=(
            CameraProfile(width, height, 30, BPP_YUYV, StreamKind.RGB),
            CameraProfile(width, height, 30, BPP_Z16_DEPTH, StreamKind.DEPTH),
        ),
        controller=controller,
        link_speed=LinkSpeed.USB3,
    )


def d415_quad_full_res() -> tuple[CameraDescriptor, ...]:
    """Four D415 color+depth at 1280×720 on one controller (`06` §2.9: ~3539 Mbps)."""
    return tuple(_d415_at(1280, 720, "usb-controller-0", i) for i in range(4))


def d415_quad_reduced() -> tuple[CameraDescriptor, ...]:
    """Four D415 color+depth at 640×360 on one controller (`06` §2.9: ~882 Mbps)."""
    return tuple(_d415_at(640, 360, "usb-controller-0", i) for i in range(4))


def capture_ts_pair(
    slop_ns: int,
    frame_count: int = 300,
    period_ns: int = NANOSECONDS_PER_MILLISECOND * 33,
) -> dict[str, list[int]]:
    """Two capture_ts streams offset by a known constant slop.

    Slot `b` trails slot `a` by exactly `slop_ns` on every frame, so the nearest-match
    slop distribution has a known answer.

    Args:
        slop_ns: Constant per-frame offset (ns) of slot `b` behind slot `a`.
        frame_count: Frames per slot.
        period_ns: Inter-frame interval (ns); default ~33 ms (30 fps).

    Returns:
        (dict[str, list[int]]) `{"a": [...], "b": [...]}`.
    """
    base = [i * period_ns for i in range(frame_count)]
    return {"a": base, "b": [t + slop_ns for t in base]}


def frame_numbers_with_drops() -> list[int]:
    """A device frame-number stream missing 3 and 7 and duplicating 5.

    Missing `{3, 7}`, duplicate `{5}` — the known answer for the continuity test.
    """
    return [0, 1, 2, 4, 5, 5, 6, 8, 9]


def index_based_binding_spec() -> dict[str, object]:
    """A binding spec that pins slots by enumeration index — must be rejected (⑧)."""
    return {"wrist": 0, "front": "1", "overhead": "/dev/video2"}


def serial_based_binding_spec() -> dict[str, object]:
    """A valid binding spec keyed by the stable serials of the webcam trio fixtures."""
    return {
        "wrist": "rs-0001",
        "front": "uvc-logitech-720",
        "fallback": "uvc-fallback-480",
    }


def udev_symlink_binding_spec() -> dict[str, object]:
    """A binding whose value is a udev by-id symlink — stable, so it must be accepted.

    FR-CAM-004 names the udev symlink as the webcam's stable identity; only a bare
    `/dev/videoN` node (an enumeration index) is forbidden. This proves the validator
    distinguishes the two.
    """
    return {"wrist": "/dev/v4l/by-id/usb-Generic_UVC_Camera-video-index0"}
