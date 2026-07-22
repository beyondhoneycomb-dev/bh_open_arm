"""Parse `lsusb -t` into the per-controller USB topology (FR-CAM-005).

A camera's uncompressed bandwidth is budgeted twice: against the aggregate and
against the *single controller* it hangs off, because two cameras sharing one USB
root hub share that hub's finite bandwidth. `lsusb -t` is where that grouping comes
from — its tree prints each controller (a root hub) with the devices beneath it —
and this module turns the tree text into a structure the budget can sum per
controller.

The boundary this module keeps honest: parsing the tree and grouping by controller
runs here, against a captured or synthetic tree. Correlating a specific camera
*serial* to a tree node needs the live `serial → bus` map udev supplies for a
physically attached camera, which this host has none of. That map is therefore an
input — supplied by a fixture here, by udev on real hardware — never fabricated, so
the deferred half stays a skip with a reason (`02a` §4.1) rather than a false green.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from backend.camera.descriptor import CameraDescriptor
from backend.sensing.bandwidth.constants import (
    CAMERA_USB_CLASS,
    CONTROLLER_ID_PREFIX,
)

# A `lsusb -t` root-hub line: `/:  Bus 003.Port 001: Dev 001, Class=root_hub,
# Driver=xhci_hcd/14p, 480M`. The driver carries a trailing `/<n>p` port count that
# is not part of the driver name, so it is captured apart from it.
_ROOT_HUB = re.compile(
    r"^/:\s+Bus\s+(?P<bus>\d+)\.Port\s+\d+:\s+Dev\s+\d+,\s+"
    r"Class=root_hub,\s+Driver=(?P<driver>\S+?)(?:/\d+p)?,\s+(?P<speed>\S+)\s*$"
)

# A device line under a root hub: `    |__ Port 010: Dev 003, If 0, Class=Hub,
# Driver=hub/4p, 480M`. The class may contain spaces (`Human Interface Device`), so
# it is matched non-greedily up to the `, Driver=` that always follows it.
_DEVICE = re.compile(
    r"^(?P<indent>\s+)\|__\s+Port\s+(?P<port>\d+):\s+Dev\s+(?P<dev>\d+),\s+"
    r"If\s+(?P<iface>\d+),\s+Class=(?P<klass>.+?),\s+"
    r"Driver=(?P<driver>\S+?)(?:/\d+p)?,\s+(?P<speed>\S+)\s*$"
)

# The advertised link speed, `480M` / `5000M` / `20000M/x2`: the leading integer is
# the megabit figure; the optional `/x2` lane suffix is not part of it.
_SPEED_MBPS = re.compile(r"^(\d+)M")


def _speed_mbps(token: str) -> int:
    """Return the megabit-per-second figure of an `lsusb -t` speed token.

    Args:
        token: A speed token such as `480M` or `20000M/x2`.

    Returns:
        (int) The advertised link speed in Mbps, or 0 when unparseable.
    """
    match = _SPEED_MBPS.match(token)
    return int(match.group(1)) if match else 0


@dataclass(frozen=True)
class UsbDevice:
    """One non-root-hub node in the USB tree.

    Attributes:
        controller_bus: Bus number of the root hub this device descends from.
        port: Port number on its parent.
        dev: Enumeration device number (transient — never an identity, FR-CAM-004).
        interface: Interface number of this tree row (one device prints per If).
        device_class: The `Class=` string, verbatim.
        driver: The bound kernel driver, or `[none]` when unbound.
        link_speed_mbps: Advertised link speed of this device.
    """

    controller_bus: int
    port: int
    dev: int
    interface: int
    device_class: str
    driver: str
    link_speed_mbps: int

    @property
    def is_camera(self) -> bool:
        """Whether this node is a UVC/RealSense video interface (best effort)."""
        return self.device_class == CAMERA_USB_CLASS


@dataclass(frozen=True)
class UsbController:
    """One USB controller — a root hub and everything beneath it.

    Attributes:
        bus: Bus number the controller owns.
        driver: Host-controller driver (`xhci_hcd`).
        link_speed_mbps: Advertised link speed of the root hub.
        devices: Non-root-hub nodes descending from this controller.
    """

    bus: int
    driver: str
    link_speed_mbps: int
    devices: tuple[UsbDevice, ...]

    @property
    def controller_id(self) -> str:
        """The `usbN` identity, matching the Linux controller device name."""
        return f"{CONTROLLER_ID_PREFIX}{self.bus}"

    def camera_devices(self) -> tuple[UsbDevice, ...]:
        """The camera-class nodes on this controller (for the topology report)."""
        return tuple(device for device in self.devices if device.is_camera)


@dataclass(frozen=True)
class UsbTopology:
    """The whole parsed `lsusb -t` tree, grouped by controller.

    Attributes:
        controllers: One entry per root hub, in tree order.
    """

    controllers: tuple[UsbController, ...]

    def controller_ids(self) -> tuple[str, ...]:
        """Every controller id present, in tree order."""
        return tuple(controller.controller_id for controller in self.controllers)

    def controller_id_for_bus(self, bus: int) -> str:
        """Return the controller id owning a bus.

        Args:
            bus: The USB bus number.

        Returns:
            (str) The `usbN` controller id.

        Raises:
            KeyError: When no controller owns the bus — a `serial → bus` map that
                names a bus absent from the tree is a mismatch, not a value to
                paper over with a default controller.
        """
        for controller in self.controllers:
            if controller.bus == bus:
                return controller.controller_id
        raise KeyError(f"bus {bus} is not present in the parsed USB topology")


def parse_lsusb_tree(text: str) -> UsbTopology:
    """Parse `lsusb -t` output into a per-controller topology.

    Each root-hub line opens a controller and every following device line, until
    the next root hub, belongs to it — the bus number appears only on the root-hub
    line, so a device inherits it from the controller currently open.

    Args:
        text: The stdout of `lsusb -t`.

    Returns:
        (UsbTopology) Controllers with their descendant devices.

    Raises:
        ValueError: When a device line appears before any root-hub line, which a
            well-formed tree never does; treating it as controllerless would drop
            the device silently from every per-controller sum.
    """
    controllers: list[UsbController] = []
    pending: list[UsbDevice] = []
    current: UsbController | None = None

    def _flush() -> None:
        if current is not None:
            controllers.append(replace(current, devices=tuple(pending)))

    for line in text.splitlines():
        if not line.strip():
            continue
        root = _ROOT_HUB.match(line)
        if root:
            _flush()
            pending = []
            current = UsbController(
                bus=int(root.group("bus")),
                driver=root.group("driver"),
                link_speed_mbps=_speed_mbps(root.group("speed")),
                devices=(),
            )
            continue
        device = _DEVICE.match(line)
        if device:
            if current is None:
                raise ValueError(f"device line precedes any root hub: {line!r}")
            pending.append(
                UsbDevice(
                    controller_bus=current.bus,
                    port=int(device.group("port")),
                    dev=int(device.group("dev")),
                    interface=int(device.group("iface")),
                    device_class=device.group("klass").strip(),
                    driver=device.group("driver"),
                    link_speed_mbps=_speed_mbps(device.group("speed")),
                )
            )
    _flush()
    return UsbTopology(controllers=tuple(controllers))


def assign_controllers(
    descriptors: Sequence[CameraDescriptor],
    topology: UsbTopology,
    serial_to_bus: Mapping[str, int],
) -> tuple[CameraDescriptor, ...]:
    """Re-stamp each descriptor's controller from the parsed topology.

    The `lsusb -t` tree carries no serial, so the join key is `serial → bus`, which
    udev supplies for a live camera and a fixture supplies here. Rewriting the
    controller field (rather than trusting whatever enumeration guessed) is what
    makes the per-controller sum reflect the physical bus the operator plugged into.

    Args:
        descriptors: Enumerated cameras to re-stamp.
        topology: The parsed USB topology.
        serial_to_bus: Each camera serial to the bus number it enumerated on.

    Returns:
        (tuple[CameraDescriptor, ...]) Descriptors with `controller` set from the tree.

    Raises:
        KeyError: When a descriptor's serial has no bus in the map — an unmapped
            camera would otherwise keep a stale controller and corrupt the sum.
    """
    stamped: list[CameraDescriptor] = []
    for descriptor in descriptors:
        if descriptor.serial not in serial_to_bus:
            raise KeyError(f"no bus mapping for camera serial {descriptor.serial!r}")
        controller_id = topology.controller_id_for_bus(serial_to_bus[descriptor.serial])
        stamped.append(replace(descriptor, controller=controller_id))
    return tuple(stamped)


def lsusb_available() -> bool:
    """Whether the `lsusb` binary is on PATH (the live-topology precondition)."""
    return shutil.which("lsusb") is not None


def run_lsusb_tree() -> str:
    """Return live `lsusb -t` output for the real-hardware topology path.

    The parser and per-controller grouping run against this on real hardware; here
    it exercises the parse against the host's own bus, while correlating a camera to
    a controller stays deferred for want of an attached camera (`02a` §4.1).

    Returns:
        (str) The stdout of `lsusb -t`.

    Raises:
        FileNotFoundError: When `lsusb` is not installed.
    """
    if not lsusb_available():
        raise FileNotFoundError("lsusb is not installed on this host")
    return subprocess.run(
        ["lsusb", "-t"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


__all__ = [
    "CAMERA_USB_CLASS",
    "UsbController",
    "UsbDevice",
    "UsbTopology",
    "assign_controllers",
    "lsusb_available",
    "parse_lsusb_tree",
    "run_lsusb_tree",
]
