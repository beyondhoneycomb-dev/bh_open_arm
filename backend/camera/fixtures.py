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

import errno
from dataclasses import dataclass

from backend.camera.constants import (
    ARDUCAM_AUTO_EXPOSURE_AUTO_MODE,
    ARDUCAM_AUTO_EXPOSURE_MANUAL,
    ARDUCAM_AUTO_EXPOSURE_MENU_ENTRIES,
    ARDUCAM_EXPOSURE_TIME_MAXIMUM,
    ARDUCAM_EXPOSURE_TIME_MINIMUM,
    ARDUCAM_GAIN_MAXIMUM,
    ARDUCAM_GAIN_MINIMUM,
    ARDUCAM_WHITE_BALANCE_AUTOMATIC_OFF,
    ARDUCAM_WHITE_BALANCE_AUTOMATIC_ON,
    ARDUCAM_WHITE_BALANCE_TEMPERATURE_DEFAULT,
    ARDUCAM_WHITE_BALANCE_TEMPERATURE_MAXIMUM,
    ARDUCAM_WHITE_BALANCE_TEMPERATURE_MINIMUM,
    BPP_RGB888,
    BPP_YUYV,
    BPP_Z16_DEPTH,
    CONTROL_AUTO_EXPOSURE,
    CONTROL_EXPOSURE_TIME_ABSOLUTE,
    CONTROL_GAIN,
    CONTROL_WHITE_BALANCE_AUTOMATIC,
    CONTROL_WHITE_BALANCE_TEMPERATURE,
    NANOSECONDS_PER_MILLISECOND,
    ZED_WHITE_BALANCE_TEMPERATURE_DEFAULT,
    ZED_WHITE_BALANCE_TEMPERATURE_MAXIMUM,
    ZED_WHITE_BALANCE_TEMPERATURE_MINIMUM,
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


@dataclass(frozen=True)
class ControlRange:
    """What one control accepts, and what has to be true before it accepts anything.

    Attributes:
        minimum: Lowest legal value; anything under it is clamped up to it.
        maximum: Highest legal value; anything over it is clamped down to it.
        gate: `(switch name, value that switch must hold)` for a control guarded by an
            automatic mode, or None when the control is always writable. The two switches on
            this model open in opposite directions — `auto_exposure` frees exposure at 1
            (Manual) while `white_balance_automatic` frees white balance at 0 (Off) — so the
            unlocking value is carried per control rather than assumed.
        legal_values: The entries a menu control offers, or None for an integer control.
            A menu's bounds do not enumerate it: `auto_exposure` reports 0..3 and answers to
            0 and 1 only, so the set is carried rather than derived. It also selects the
            failure: a menu refuses an entry it does not have, where an integer clamps.
    """

    minimum: int
    maximum: int
    gate: tuple[str, int] | None
    legal_values: tuple[int, ...] | None = None


class FakeCameraControls:
    """A stand-in device that reproduces the three answers a V4L2 write gives.

    Only one of the three is silent, and that one is why the readback check exists: an
    out-of-range value on an integer control is clamped to the nearest legal one and reported
    as success. The other two are refusals — EACCES for a write to a control its automatic mode
    still holds inactive, EINVAL for a menu entry the device does not have — and they are
    modelled because a caller written against a fake that never raises has no error branch for
    them, which is the same as not handling them.

    An unknown control name raises `KeyError` instead of being absorbed — deciding what a device
    does not have belongs to the planning step, and a fake that quietly swallowed it would hide
    a plan that skipped nothing.
    """

    def __init__(self, ranges: dict[str, ControlRange], values: dict[str, int]) -> None:
        self._ranges = ranges
        self._values = dict(values)

    def read(self) -> dict[str, int]:
        """Return every control this device exposes and its current value."""
        return dict(self._values)

    def write(self, name: str, value: int) -> None:
        """Apply a write the way the driver answers it.

        Args:
            name: The control name.
            value: The value to write, in the control's own units.

        Raises:
            KeyError: If this device has no such control.
            PermissionError: EACCES — the control is held inactive by its automatic mode.
            OSError: EINVAL — the value names a menu entry this device does not offer.
        """
        control = self._ranges[name]
        if control.gate is not None:
            switch_name, unlocking_value = control.gate
            if self._values[switch_name] != unlocking_value:
                raise PermissionError(
                    errno.EACCES,
                    f"{name} is inactive while {switch_name} holds "
                    f"{self._values[switch_name]}, not {unlocking_value}",
                )
        if control.legal_values is not None:
            if value not in control.legal_values:
                raise OSError(
                    errno.EINVAL,
                    f"{name} has no entry {value}; it offers {list(control.legal_values)}",
                )
            self._values[name] = value
            return
        self._values[name] = max(control.minimum, min(control.maximum, value))


def arducam_control_set() -> FakeCameraControls:
    """A B0495 in the state it powers up in: both automatic modes on, both drivers at minimum.

    Powering up at the minimum is what makes the fake worth running: exposure and gain each
    report their floor as the current value, so a declaration that failed to land leaves the
    camera darker than declared rather than at the value someone meant to set. No focus control
    appears, because this model has none (fixed M12 lens).
    """
    ranges = {
        CONTROL_AUTO_EXPOSURE: ControlRange(
            ARDUCAM_AUTO_EXPOSURE_AUTO_MODE,
            max(ARDUCAM_AUTO_EXPOSURE_MENU_ENTRIES),
            None,
            ARDUCAM_AUTO_EXPOSURE_MENU_ENTRIES,
        ),
        CONTROL_WHITE_BALANCE_AUTOMATIC: ControlRange(
            ARDUCAM_WHITE_BALANCE_AUTOMATIC_OFF, ARDUCAM_WHITE_BALANCE_AUTOMATIC_ON, None
        ),
        CONTROL_EXPOSURE_TIME_ABSOLUTE: ControlRange(
            ARDUCAM_EXPOSURE_TIME_MINIMUM,
            ARDUCAM_EXPOSURE_TIME_MAXIMUM,
            (CONTROL_AUTO_EXPOSURE, ARDUCAM_AUTO_EXPOSURE_MANUAL),
        ),
        CONTROL_GAIN: ControlRange(ARDUCAM_GAIN_MINIMUM, ARDUCAM_GAIN_MAXIMUM, None),
        CONTROL_WHITE_BALANCE_TEMPERATURE: ControlRange(
            ARDUCAM_WHITE_BALANCE_TEMPERATURE_MINIMUM,
            ARDUCAM_WHITE_BALANCE_TEMPERATURE_MAXIMUM,
            (CONTROL_WHITE_BALANCE_AUTOMATIC, ARDUCAM_WHITE_BALANCE_AUTOMATIC_OFF),
        ),
    }
    values = {
        CONTROL_AUTO_EXPOSURE: ARDUCAM_AUTO_EXPOSURE_AUTO_MODE,
        CONTROL_WHITE_BALANCE_AUTOMATIC: ARDUCAM_WHITE_BALANCE_AUTOMATIC_ON,
        CONTROL_EXPOSURE_TIME_ABSOLUTE: ARDUCAM_EXPOSURE_TIME_MINIMUM,
        CONTROL_GAIN: ARDUCAM_GAIN_MINIMUM,
        CONTROL_WHITE_BALANCE_TEMPERATURE: ARDUCAM_WHITE_BALANCE_TEMPERATURE_DEFAULT,
    }
    return FakeCameraControls(ranges, values)


def zed_uvc_control_set() -> FakeCameraControls:
    """A ZED-M over UVC, which exposes no exposure controls at all — those live in its SDK.

    Its white balance floor is not the wrist pair's, so the bounds come from its own constants;
    sharing them would let a declaration that is legal on one camera and not on the other pass
    every case here.
    """
    ranges = {
        CONTROL_WHITE_BALANCE_AUTOMATIC: ControlRange(
            ARDUCAM_WHITE_BALANCE_AUTOMATIC_OFF, ARDUCAM_WHITE_BALANCE_AUTOMATIC_ON, None
        ),
        CONTROL_WHITE_BALANCE_TEMPERATURE: ControlRange(
            ZED_WHITE_BALANCE_TEMPERATURE_MINIMUM,
            ZED_WHITE_BALANCE_TEMPERATURE_MAXIMUM,
            (CONTROL_WHITE_BALANCE_AUTOMATIC, ARDUCAM_WHITE_BALANCE_AUTOMATIC_OFF),
        ),
    }
    values = {
        CONTROL_WHITE_BALANCE_AUTOMATIC: ARDUCAM_WHITE_BALANCE_AUTOMATIC_ON,
        CONTROL_WHITE_BALANCE_TEMPERATURE: ZED_WHITE_BALANCE_TEMPERATURE_DEFAULT,
    }
    return FakeCameraControls(ranges, values)
