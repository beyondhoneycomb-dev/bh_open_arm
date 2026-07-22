"""Scenario builders for the WP-3B-01 tolerant-connect tests.

Every camera here is the frozen synthetic fixture (`contracts/fixtures`) or a
hand-built `CameraDescriptor` with a known answer, so the tests assert exact
dispositions rather than opaque behaviour. Kept out of a `test_` module so pytest
does not collect it.
"""

from __future__ import annotations

from backend.camera.descriptor import (
    CameraDescriptor,
    CameraProfile,
    CameraType,
    LinkSpeed,
    StreamKind,
)
from contracts.camera_registry import CameraRegistry, CameraSpec
from contracts.fixtures.synthetic_camera import SyntheticCamera
from contracts.prim import REQUIRED_FRAME_TYPE, CameraSlotKey


def spec(slot: str) -> CameraSpec:
    """A configured RGB camera spec for one slot."""
    return CameraSpec(
        slot=CameraSlotKey(slot),
        capabilities=frozenset({REQUIRED_FRAME_TYPE}),
        width=640,
        height=480,
        fps=30,
    )


def registry_with(*slots: str) -> CameraRegistry:
    """A `CTR-CAM@v1` registry holding one camera per slot."""
    registry = CameraRegistry()
    for slot in slots:
        registry.register(spec(slot))
    return registry


def live_camera(slot: str) -> SyntheticCamera:
    """A synthetic camera that delivers a frame at every index."""
    return SyntheticCamera(spec=spec(slot))


def dead_camera(slot: str, window: int = 5) -> SyntheticCamera:
    """A synthetic camera whose frames are all dropped across the probe window."""
    return SyntheticCamera(spec=spec(slot), dropped_indices=frozenset(range(window)))


class RaisingProbe:
    """A probe whose open raises — the driver-hang case a tolerant connect must absorb."""

    def read_latest(self, up_to_index: int) -> object | None:
        """Raise as if the device errored on grab."""
        raise RuntimeError("device busy")


def usb2_descriptor(serial: str, *, heavy: bool) -> CameraDescriptor:
    """A USB2-fallback webcam descriptor; `heavy` picks a profile over the 480 Mbps budget.

    Light: 640x480 YUYV @30 = 147.5 Mbps (fits). Heavy: 1280x720 RGB888 @30 = 663 Mbps
    (over the USB2 nominal budget, so it is the profile the block refuses).
    """
    profile = (
        CameraProfile(1280, 720, 30, 3, StreamKind.RGB)
        if heavy
        else CameraProfile(640, 480, 30, 2, StreamKind.RGB)
    )
    return CameraDescriptor(
        serial=serial,
        camera_type=CameraType.OPENCV,
        model="Generic UVC",
        profiles=(profile,),
        controller="usb-controller-2",
        link_speed=LinkSpeed.USB2,
    )
