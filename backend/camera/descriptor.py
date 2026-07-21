"""The camera-descriptor data model the whole enumerate/measure layer operates on.

A descriptor is the enumeration result for one physical camera (`06` FR-CAM-002):
its stable serial, backend type, model, the profiles it currently streams, the USB
controller it hangs off, and its negotiated link speed. Every calculator in this
package takes descriptors — never a live camera handle — so the synthetic-fixture
corpus and a real capture flow through identical code (`02a` §4.1 re-verification).

The types are frozen and validate on construction. The one invariant they enforce
here, rather than downstream, is FR-CAM-004: a camera is identified by a *serial*,
never by an enumeration index. An int where a serial belongs is a construction error,
not a value to be coerced.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any


class CameraType(Enum):
    """Backend the camera is driven through (`06` FR-CAM-002)."""

    OPENCV = "opencv"
    INTEL_REALSENSE = "intelrealsense"


class LinkSpeed(Enum):
    """Negotiated USB link speed. A USB2 value is the fallback FR-CAM-003 flags."""

    USB2 = "usb2"
    USB3 = "usb3"


class StreamKind(Enum):
    """Which stream a profile describes. Depth counts as its own stream for the
    bandwidth sum (`06` FR-CAM-010: depth-on RealSense = color + depth)."""

    RGB = "rgb"
    DEPTH = "depth"


@dataclass(frozen=True)
class CameraProfile:
    """One negotiated (resolution × fps) stream of a camera.

    `bpp` is the bytes-per-pixel of the *negotiated pixel format*, not a property of
    the camera: `06` §2.9's own worked examples only agree when Bpp travels with the
    format (YUYV/z16 = 2, RGB888 = 3). Keeping it a field is what lets the bandwidth
    formula reproduce all three spec figures without baking a wrong constant.

    Attributes:
        width: Frame width in pixels.
        height: Frame height in pixels.
        fps: Target frames per second.
        bpp: Bytes per pixel of the negotiated format.
        stream_kind: RGB or depth.
    """

    width: int
    height: int
    fps: int
    bpp: int
    stream_kind: StreamKind

    def __post_init__(self) -> None:
        for name, value in (
            ("width", self.width),
            ("height", self.height),
            ("fps", self.fps),
            ("bpp", self.bpp),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"CameraProfile.{name} must be a positive int, got {value!r}")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> CameraProfile:
        """Build a profile from a JSON-shaped mapping (real-fixture ingest path)."""
        return cls(
            width=int(raw["width"]),
            height=int(raw["height"]),
            fps=int(raw["fps"]),
            bpp=int(raw["bpp"]),
            stream_kind=StreamKind(raw["stream_kind"]),
        )


class SerialBindingError(ValueError):
    """A descriptor was given an index where a stable serial is required (FR-CAM-004)."""


@dataclass(frozen=True)
class CameraDescriptor:
    """Enumeration result for one physical camera.

    Attributes:
        serial: Stable identifier — RealSense `serial_number_or_name` or a webcam
            udev symlink (`06` FR-CAM-004). Never an enumeration index.
        camera_type: Driving backend.
        model: Human-readable model string.
        profiles: Currently streamed profiles; depth adds a second profile.
        controller: USB root-hub / controller id the camera hangs off (FR-CAM-005).
        link_speed: Negotiated link speed.
    """

    serial: str
    camera_type: CameraType
    model: str
    profiles: tuple[CameraProfile, ...]
    controller: str
    link_speed: LinkSpeed

    def __post_init__(self) -> None:
        # Validate the runtime value, not the declared type: FR-CAM-004 forbids an
        # enumeration index, and a positional constructor can still be handed one
        # despite the `str` annotation, so the guard reads through an `object` view.
        serial_value: object = self.serial
        if isinstance(serial_value, (bool, int)) or not isinstance(serial_value, str):
            raise SerialBindingError(
                f"serial must be a stable string, not an enumeration index: {self.serial!r}"
            )
        if not self.serial.strip():
            raise SerialBindingError("serial must be a non-empty string")
        if not self.profiles:
            raise ValueError(f"camera {self.serial!r} has no profiles")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> CameraDescriptor:
        """Build a descriptor from a JSON-shaped mapping (real-fixture ingest path).

        A `serial` field that parses as a bare integer is rejected here, so a real
        capture that recorded index-based identity cannot slip past FR-CAM-004.
        """
        serial = raw.get("serial")
        if isinstance(serial, (bool, int)):
            raise SerialBindingError(
                f"captured serial is an enumeration index, not a stable id: {serial!r}"
            )
        return cls(
            serial=str(serial),
            camera_type=CameraType(raw["camera_type"]),
            model=str(raw["model"]),
            profiles=tuple(CameraProfile.from_mapping(p) for p in raw["profiles"]),
            controller=str(raw["controller"]),
            link_speed=LinkSpeed(raw["link_speed"]),
        )
