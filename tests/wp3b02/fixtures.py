"""Synthetic corpus for the WP-3B-02 budget block: a USB tree and matching cameras.

The camera descriptors reuse the WP-0B-08 profile constants (`06` §2.9's figures)
so the expected sums are the specification's own arithmetic, not numbers invented
here. The `lsusb -t` text is a captured-shape tree — two cameras sharing one root
hub, one on another — paired with the `serial → bus` map udev would supply for those
same cameras, which is the input this host cannot obtain from real hardware.
"""

from __future__ import annotations

from backend.camera.descriptor import (
    CameraDescriptor,
    CameraProfile,
    CameraType,
    LinkSpeed,
)
from backend.camera.fixtures import DEPTH_640_480_30, YUYV_640_480_30

# Two cameras on bus 3 (usb3), one on bus 4 (usb4): the shared-controller case
# FR-CAM-005 budgets, expressed in the exact line shape `lsusb -t` prints.
SYNTHETIC_TREE = (
    "/:  Bus 003.Port 001: Dev 001, Class=root_hub, Driver=xhci_hcd/6p, 5000M\n"
    "    |__ Port 002: Dev 010, If 0, Class=Video, Driver=uvcvideo, 5000M\n"
    "    |__ Port 003: Dev 011, If 0, Class=Video, Driver=uvcvideo, 5000M\n"
    "/:  Bus 004.Port 001: Dev 001, Class=root_hub, Driver=xhci_hcd/4p, 5000M\n"
    "    |__ Port 001: Dev 012, If 0, Class=Video, Driver=uvcvideo, 5000M\n"
)

SERIAL_SHARED_A = "cam-shared-a"
SERIAL_SHARED_B = "cam-shared-b"
SERIAL_SOLO_C = "cam-solo-c"

# The `serial → bus` map udev would produce for the three cameras above. A and B
# share bus 3; C is alone on bus 4.
SYNTHETIC_SERIAL_TO_BUS = {
    SERIAL_SHARED_A: 3,
    SERIAL_SHARED_B: 3,
    SERIAL_SOLO_C: 4,
}


def _rgb_camera(serial: str, controller: str) -> CameraDescriptor:
    """A UVC webcam streaming one 640×480 YUYV stream (`06` §2.9: 147.5 Mbps)."""
    return CameraDescriptor(
        serial=serial,
        camera_type=CameraType.OPENCV,
        model="Generic UVC",
        profiles=(YUYV_640_480_30,),
        controller=controller,
        link_speed=LinkSpeed.USB3,
    )


def topology_cameras() -> tuple[CameraDescriptor, ...]:
    """Three cameras whose controllers are deliberately wrong until reconciled.

    Each is stamped `unassigned` so a test proves the topology reconciliation, not
    a controller that happened to be right already, is what groups them by bus.
    """
    return (
        _rgb_camera(SERIAL_SHARED_A, "unassigned"),
        _rgb_camera(SERIAL_SHARED_B, "unassigned"),
        _rgb_camera(SERIAL_SOLO_C, "unassigned"),
    )


def realsense_rgb_or_rgbd(serial: str, controller: str, *, depth: bool) -> CameraDescriptor:
    """A RealSense at 640×480@30, color only or color+depth (the depth toggle).

    With `depth=True` the descriptor carries a second profile, so its bandwidth is
    the sum of two streams — the exact behaviour that must flip an otherwise-passing
    configuration into a blocked one (`02b` WP-3B-02 ②).

    Args:
        serial: Stable camera serial.
        controller: Controller id to place the camera on.
        depth: Whether depth streaming is on (adds the second stream).

    Returns:
        (CameraDescriptor) The color-only or color+depth RealSense.
    """
    profiles: tuple[CameraProfile, ...] = (YUYV_640_480_30,)
    if depth:
        profiles = (YUYV_640_480_30, DEPTH_640_480_30)
    return CameraDescriptor(
        serial=serial,
        camera_type=CameraType.INTEL_REALSENSE,
        model="Intel RealSense D435",
        profiles=profiles,
        controller=controller,
        link_speed=LinkSpeed.USB3,
    )


def realsense_trio(*, depth: bool) -> tuple[CameraDescriptor, ...]:
    """Three RealSense on one controller, color-only or color+depth.

    Color-only each is 147.5 Mbps (sum 442.5); with depth each is 295 Mbps (sum
    885). A cap between the two sums is what makes the depth toggle decide the block.
    """
    return tuple(
        realsense_rgb_or_rgbd(f"rs-trio-{index}", "usb3", depth=depth) for index in range(3)
    )


# Depth-on/off sums for the trio, straddled by a chosen cap in the block tests.
STREAM_DEPTH_OFF_MBPS = 3 * 147.456
STREAM_DEPTH_ON_MBPS = 6 * 147.456
FLIP_CAP_MBPS = 600.0
