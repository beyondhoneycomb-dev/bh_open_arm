"""Identify a camera by the USB port it hangs off, for cameras a serial cannot tell apart.

`06` FR-CAM-004 binds a slot by a stable identifier and never by enumeration index, and names
the udev symlink as the webcam mechanism. That mechanism assumes distinct serials, and the
wrist pair on this rig does not have them: both Arducam B0495 report
`Arducam_202500915_0001`, so udev writes one `/dev/v4l/by-id/` entry and the second camera
gets no stable name at all. `06` FR-CAM-085 is the spec's own acknowledgement of this — and it
files serial-burning as priority C, explicitly not the canonical contract.

What this module binds on instead is `bus_info` from `VIDIOC_QUERYCAP`: the controller and
port path the kernel itself reports for the node. It is stable across reboot and across
re-plugging into the same port, it distinguishes two cameras with one serial, and it needs no
udev rule to exist. It moves when the operator moves the plug — the same property, and the
same failure mode, as the CAN channel binding's `ID_PATH`.

The capability is read rather than inferred. A UVC camera presents two nodes and only the
first captures; which index that is, is a driver detail, so the node is asked instead of
guessed. `V4L2_CAP_VIDEO_CAPTURE` on `device_caps` — the per-node field, not the
whole-device `capabilities` — is the answer.
"""

from __future__ import annotations

import fcntl
import os
import struct
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

# `VIDIOC_QUERYCAP` is `_IOR('V', 0, struct v4l2_capability)`. Linux packs an ioctl request as
# direction(2) | size(14) | type(8) | number(8); read-only is direction 2.
_IOCTL_DIRECTION_READ = 2
_IOCTL_DIRECTION_SHIFT = 30
_IOCTL_SIZE_SHIFT = 16
_IOCTL_TYPE_SHIFT = 8
_V4L2_IOCTL_TYPE = ord("V")
_QUERYCAP_NUMBER = 0

# `struct v4l2_capability`: driver[16], card[32], bus_info[32], version, capabilities,
# device_caps, reserved[3].
_CAPABILITY_STRUCT_BYTES = 104
_CAPABILITY_HEAD = "16s32s32sII"

VIDIOC_QUERYCAP = (
    (_IOCTL_DIRECTION_READ << _IOCTL_DIRECTION_SHIFT)
    | (_CAPABILITY_STRUCT_BYTES << _IOCTL_SIZE_SHIFT)
    | (_V4L2_IOCTL_TYPE << _IOCTL_TYPE_SHIFT)
    | _QUERYCAP_NUMBER
)

# Set on `device_caps` when this node delivers video frames rather than metadata.
V4L2_CAP_VIDEO_CAPTURE = 0x00000001

# Where the kernel publishes the nodes, and the name they take.
VIDEO_DEVICE_ROOT = Path("/dev")
VIDEO_DEVICE_GLOB = "video*"


class CameraPortError(RuntimeError):
    """A camera cannot be identified by its port."""


class AmbiguousCameraPortError(CameraPortError):
    """Two capture nodes report the same port, so a binding to it names neither.

    Separate from a missing camera: an absent port fails the lookup loudly, while a duplicated
    one would resolve to whichever node was enumerated first and silently swap the two slots
    the next time the order changed.
    """


@dataclass(frozen=True)
class CaptureNode:
    """One video node that delivers frames, and the port it hangs off.

    Attributes:
        device: The `/dev/videoN` node. Held for opening, never for binding — the number moves.
        port_path: `bus_info` from the driver, e.g. `usb-0000:00:0d.0-1.1.3.3`. This is what a
            slot binds to.
        card: The driver's human name for the camera, for showing the operator which is which.
    """

    device: Path
    port_path: str
    card: str


def _decode(raw: bytes) -> str:
    """Return a NUL-padded kernel string as text."""
    return raw.rstrip(b"\0").decode("utf-8", errors="replace")


def query_capture_node(device: Path) -> CaptureNode | None:
    """Ask one video node whether it captures, and on what port.

    Opened non-blocking and read-only: `QUERYCAP` does not start a stream, so probing must not
    take the camera away from whatever is streaming it.

    Args:
        device: The `/dev/videoN` node to ask.

    Returns:
        (CaptureNode | None) The node's identity, or None when it delivers no video — a
        metadata node, or one that cannot be opened or queried on this host.
    """
    try:
        descriptor = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        answer = fcntl.ioctl(descriptor, VIDIOC_QUERYCAP, bytes(_CAPABILITY_STRUCT_BYTES))
    except OSError:
        return None
    finally:
        os.close(descriptor)

    _driver, card, bus_info, _version, _capabilities = struct.unpack_from(_CAPABILITY_HEAD, answer)
    (device_caps,) = struct.unpack_from("I", answer, struct.calcsize(_CAPABILITY_HEAD))
    if not device_caps & V4L2_CAP_VIDEO_CAPTURE:
        return None
    return CaptureNode(device=device, port_path=_decode(bus_info), card=_decode(card))


def video_device_nodes(root: Path = VIDEO_DEVICE_ROOT) -> tuple[Path, ...]:
    """Return the video nodes present under a device root, in a stable order.

    Args:
        root: The device directory; the real one by default.

    Returns:
        (tuple[Path, ...]) Every `videoN` node, sorted by its number so the order is the
        kernel's rather than the filesystem's.
    """
    nodes = list(root.glob(VIDEO_DEVICE_GLOB))
    return tuple(sorted(nodes, key=lambda node: (len(node.name), node.name)))


def enumerate_capture_nodes(root: Path = VIDEO_DEVICE_ROOT) -> tuple[CaptureNode, ...]:
    """Enumerate every video node on this host that actually captures.

    Args:
        root: The device directory to enumerate.

    Returns:
        (tuple[CaptureNode, ...]) The capturing nodes, metadata siblings dropped.
    """
    found = (query_capture_node(node) for node in video_device_nodes(root))
    return tuple(node for node in found if node is not None)


def discovery_rows(nodes: Sequence[CaptureNode]) -> tuple[dict[str, str], ...]:
    """Render the discovered cameras as the rows the camera screen assigns against.

    The port leads and the card follows, because the card is the same string on both wrist
    cameras and the port is the only field that separates them. The device node travels for
    diagnosis and is never the identity: it renumbers between boots.

    Args:
        nodes: The capture nodes enumerated this scan.

    Returns:
        (tuple[dict[str, str], ...]) One row per camera, ordered by port so the screen's list
        does not reshuffle between scans.

    Raises:
        AmbiguousCameraPortError: If two cameras report one port, so no row identifies one
            camera and the operator would be assigning a slot to whichever answered first.
    """
    assert_ports_distinguish(nodes)
    return tuple(
        {"port_path": node.port_path, "card": node.card, "device_path": str(node.device)}
        for node in sorted(nodes, key=lambda node: node.port_path)
    )


def assert_ports_distinguish(nodes: Sequence[CaptureNode]) -> None:
    """Refuse a camera set whose ports do not tell its cameras apart.

    Args:
        nodes: The capture nodes a binding would be written over.

    Raises:
        AmbiguousCameraPortError: If two nodes report one port.
    """
    seen = [node.port_path for node in nodes]
    duplicated = sorted({port for port in seen if seen.count(port) > 1})
    if duplicated:
        raise AmbiguousCameraPortError(
            f"these ports carry more than one capture node: {', '.join(duplicated)}; a slot "
            "bound to one of them names whichever node enumerated first, which is the "
            "enumeration index FR-CAM-004 refuses, wearing a port path"
        )


def node_by_port(nodes: Sequence[CaptureNode], port_path: str) -> CaptureNode:
    """Resolve a bound port back to the node currently on it.

    Args:
        nodes: The capture nodes present now.
        port_path: The port a slot was bound to.

    Returns:
        (CaptureNode) The node on that port.

    Raises:
        AmbiguousCameraPortError: If the present set does not distinguish its ports.
        CameraPortError: If nothing is on that port — the camera was unplugged, or moved to a
            different one, and opening whatever else is present would stream the wrong camera
            into the slot.
    """
    assert_ports_distinguish(nodes)
    for node in nodes:
        if node.port_path == port_path:
            return node
    present = ", ".join(sorted(node.port_path for node in nodes)) or "nothing"
    raise CameraPortError(
        f"no capture node is on port {port_path!r}; present ports are {present}. The camera "
        "was unplugged or moved — rebind it rather than opening whichever camera is there now"
    )
