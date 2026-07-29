"""How a depth camera is attached to USB, read from the kernel's own descriptors.

A depth camera can be plugged in, powered, correctly named in `lsusb` and still deliver
no depth. The stereo pair travels on a video-class interface that the camera publishes
only over a SuperSpeed link; on a full-speed one it publishes its HID control interface
alone, and there is no stream for the vendor SDK to open. Nothing on the software side
shows this — the SDK imports, the device enumerates, the serial number reads back — so
a deferral that lists only the missing SDK and the missing LeRobot class describes a rig
that would still produce no depth after both are cleared.

`06` §2.4 gates depth on API presence, which is a question about the *runtime*. This
module answers the separate question about the *cabling*, and the two are independent:
either alone is enough to stop depth.

The fields come from sysfs rather than from `lsusb`, because they are the same kernel
values and `usbutils` is not a declared dependency of this platform.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# The kernel's USB tree. Each entry is either a device or one of its interfaces; an
# interface directory is a child of its device's, named `<device>:<config>.<interface>`.
USB_SYSFS_ROOT = Path("/sys/bus/usb/devices")

# USB base class 0Eh, the class an image-carrying interface enumerates as. Depth needs
# one of these; the HID class a ZED publishes on an under-speed link is not one, and its
# presence is what makes "the camera is listed" not mean "the camera can stream".
USB_VIDEO_INTERFACE_CLASS = "0e"

_VENDOR_FIELD = "idVendor"
_PRODUCT_FIELD = "idProduct"
_SPEED_FIELD = "speed"
_INTERFACE_CLASS_FIELD = "bInterfaceClass"


@dataclass(frozen=True)
class UsbDepthLink:
    """One camera's USB attachment as the kernel enumerated it.

    Attributes:
        present: A device carrying the probed vendor/product pair was found.
        link_speed_mbps: Negotiated link speed in Mbit/s; None when the device is absent
            or the kernel published no speed for it.
        interface_classes: `bInterfaceClass` of every interface the device published,
            lower-case hex, in sysfs order.
    """

    present: bool
    link_speed_mbps: int | None
    interface_classes: tuple[str, ...]

    @property
    def carries_video(self) -> bool:
        """Whether the device published an interface a depth stream could travel on."""
        return USB_VIDEO_INTERFACE_CLASS in self.interface_classes


def _read_field(directory: Path, field: str) -> str | None:
    """Read one sysfs attribute, treating an unreadable one as absent.

    Attributes vanish between the directory listing and the read when a device is
    unplugged mid-probe, and some are unreadable to an unprivileged process; neither is
    a reason to fail a report whose whole purpose is to describe what is there.
    """
    try:
        return (directory / field).read_text(encoding="utf-8").strip().lower()
    except OSError:
        return None


def _interface_classes(device_dir: Path) -> tuple[str, ...]:
    """The interface classes one device published, in sysfs order."""
    found: list[str] = []
    for interface_dir in sorted(device_dir.glob(f"{device_dir.name}:*")):
        interface_class = _read_field(interface_dir, _INTERFACE_CLASS_FIELD)
        if interface_class is not None:
            found.append(interface_class)
    return tuple(found)


def probe_usb_link(usb_id: tuple[str, str], sysfs_root: Path = USB_SYSFS_ROOT) -> UsbDepthLink:
    """Report how a vendor/product pair is attached, if the kernel enumerated it at all.

    Args:
        usb_id: `(vendor, product)`, as the four-hex-digit strings sysfs stores.
        sysfs_root: The USB tree to read; the kernel's own by default, and a written one
            in tests, since the attachment being described is the machine's own.

    Returns:
        (UsbDepthLink) The attachment; `present` is False when nothing matched, which
        includes a host that has no USB tree at all.
    """
    vendor = usb_id[0].lower()
    product = usb_id[1].lower()
    try:
        entries = sorted(sysfs_root.iterdir())
    except OSError:
        entries = []
    for entry in entries:
        if _read_field(entry, _VENDOR_FIELD) != vendor:
            continue
        if _read_field(entry, _PRODUCT_FIELD) != product:
            continue
        speed = _read_field(entry, _SPEED_FIELD)
        return UsbDepthLink(
            present=True,
            link_speed_mbps=int(speed) if speed is not None and speed.isdigit() else None,
            interface_classes=_interface_classes(entry),
        )
    return UsbDepthLink(present=False, link_speed_mbps=None, interface_classes=())
