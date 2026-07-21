"""Parser for the USB topology tree (`lsusb -t`) and CAN-adapter membership.

`06` FR-CAM-005 and `WP-0B-06` acceptance ② require the root-hub/controller each CAN
adapter hangs off, and an explicit statement of whether the two adapters share a
controller — because two adapters on one xHCI controller share that controller's
bandwidth and scheduling, which is the whole reason the topology is recorded.
Acceptance ⑥ additionally wants the link speed logged, to confirm the `16` §10.1
claim that the Pibiger SavvyCAN-FD-X2 enumerates as High-Speed USB 2.0 (480 Mbps).

`lsusb -t` is the source because it is the one view that shows the controller
(`Driver=xhci_hcd`), the tree position, and the per-device link speed together.
This module parses that text into a tree and answers the membership question; it is
pure string processing, so it runs on synthetic fixtures here and on real `lsusb -t`
output the moment the re-verification hook is handed one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# The in-tree driver the SavvyCAN-FD-X2 binds (`16` §10.1, `gs_usb`). Adapter
# membership is resolved by matching this driver rather than a VID/PID, because the
# two adapters share a VID/PID (`16` M-12) and the driver is what marks a CAN node.
CAN_ADAPTER_DRIVER = "gs_usb"

# The link-speed token High-Speed USB 2.0 advertises in `lsusb -t` (480 Mbps). Its
# presence on an adapter's line is the measured confirmation acceptance ⑥ asks for.
HIGH_SPEED_USB2_TOKEN = "480M"

# A bus (root hub) line: `/:  Bus 002.Port 001: Dev 001, Class=root_hub,
# Driver=xhci_hcd/4p, 480M`. The driver names the host controller instance, so two
# adapters sharing a controller are two adapters whose ancestor bus line is the same.
_BUS_LINE = re.compile(
    r"^/:\s+Bus\s+(?P<bus>\d+)\.Port\s+(?P<port>\d+):\s+Dev\s+(?P<dev>\d+),\s+"
    r"Class=(?P<cls>[^,]+),\s+Driver=(?P<driver>[^,]+)(?:,\s+(?P<speed>\S+))?\s*$"
)
# A device line, indented under its bus: `    |__ Port 002: Dev 003, If 0,
# Class=Communications, Driver=gs_usb, 480M`.
_DEV_LINE = re.compile(
    r"^\s*\|__\s+Port\s+(?P<port>\d+):\s+Dev\s+(?P<dev>\d+),\s+If\s+(?P<intf>\d+),\s+"
    r"Class=(?P<cls>[^,]+),\s+Driver=(?P<driver>[^,]+)(?:,\s+(?P<speed>\S+))?\s*$"
)


@dataclass(frozen=True)
class UsbNode:
    """One USB device interface hanging off a controller.

    Attributes:
        port: Port number on its parent.
        dev: Device number on the bus.
        interface: Interface (`If`) number.
        cls: USB class string, e.g. "Communications".
        driver: Bound kernel driver, e.g. "gs_usb".
        link_speed: Advertised link speed token (e.g. "480M"), or None.
    """

    port: int
    dev: int
    interface: int
    cls: str
    driver: str
    link_speed: str | None


@dataclass
class UsbBus:
    """A root hub / host-controller instance and the devices under it.

    In `lsusb -t` each `/:` line is one root hub, and the bus number is its unique
    instance identity — the `Driver=` string (e.g. "xhci_hcd/4p") is the driver name
    plus port count and is *not* unique, since two distinct root hubs report the
    same string. Two adapters are therefore "on the same controller" when their bus
    numbers match, which is also the granularity at which they contend for bandwidth.

    Attributes:
        bus: Bus number — the root-hub/controller instance identity.
        controller: Host-controller driver string, e.g. "xhci_hcd/4p" (display only).
        link_speed: Root-hub advertised speed token, or None.
        nodes: Device interfaces under this bus, in appearance order.
    """

    bus: int
    controller: str
    link_speed: str | None
    nodes: list[UsbNode] = field(default_factory=list)


@dataclass(frozen=True)
class AdapterLocation:
    """Where one CAN adapter interface sits in the topology.

    Attributes:
        bus: Its bus number — the root-hub/controller instance it belongs to.
        controller: Its host-controller driver string (display only; not unique).
        port: Its port on the bus.
        dev: Its device number.
        interface: Its interface number.
        link_speed: Its advertised link speed token, or None.
        is_high_speed_usb2: True when the link speed is the 480 Mbps HS USB 2.0 token.
    """

    bus: int
    controller: str
    port: int
    dev: int
    interface: int
    link_speed: str | None
    is_high_speed_usb2: bool


@dataclass(frozen=True)
class TopologyReport:
    """The `usb_topology.json` payload: the tree plus the adapter-membership verdict.

    Attributes:
        buses: Every parsed bus/controller.
        adapters: The CAN-adapter interfaces found, in appearance order.
        shared_controller: True when every adapter sits on one controller instance.
            None when fewer than two adapters were found (nothing to share).
        all_high_speed_usb2: True when every adapter advertises HS USB 2.0.
    """

    buses: tuple[UsbBus, ...]
    adapters: tuple[AdapterLocation, ...]
    shared_controller: bool | None
    all_high_speed_usb2: bool

    def as_dict(self) -> dict[str, object]:
        """Project to the `usb_topology.json` structure.

        Returns:
            (dict[str, object]) Tree and membership verdict as plain data.
        """
        return {
            "buses": [
                {
                    "bus": bus.bus,
                    "controller": bus.controller,
                    "link_speed": bus.link_speed,
                    "nodes": [
                        {
                            "port": n.port,
                            "dev": n.dev,
                            "interface": n.interface,
                            "class": n.cls,
                            "driver": n.driver,
                            "link_speed": n.link_speed,
                        }
                        for n in bus.nodes
                    ],
                }
                for bus in self.buses
            ],
            "adapters": [
                {
                    "bus": a.bus,
                    "controller": a.controller,
                    "port": a.port,
                    "dev": a.dev,
                    "interface": a.interface,
                    "link_speed": a.link_speed,
                    "is_high_speed_usb2": a.is_high_speed_usb2,
                }
                for a in self.adapters
            ],
            "shared_controller": self.shared_controller,
            "all_high_speed_usb2": self.all_high_speed_usb2,
        }


def parse_topology(lsusb_t_output: str, adapter_driver: str = CAN_ADAPTER_DRIVER) -> TopologyReport:
    """Parse `lsusb -t` output into a bus tree and resolve CAN-adapter membership.

    Buses are tracked in appearance order and each device line attaches to the most
    recent bus, which is how `lsusb -t` nests them. Adapters are the device
    interfaces whose bound driver is `adapter_driver`; their controller is the
    controller of the bus they hang under, so the shared-controller question reduces
    to whether those bus identities are all equal.

    Args:
        lsusb_t_output: Raw `lsusb -t` text.
        adapter_driver: Driver that marks a CAN adapter interface.

    Returns:
        (TopologyReport) The tree, the adapter locations, and the membership verdict.
    """
    buses: list[UsbBus] = []
    adapters: list[AdapterLocation] = []
    current: UsbBus | None = None

    for line in lsusb_t_output.splitlines():
        bus_match = _BUS_LINE.match(line)
        if bus_match:
            current = UsbBus(
                bus=int(bus_match.group("bus")),
                controller=bus_match.group("driver").strip(),
                link_speed=_speed(bus_match.group("speed")),
            )
            buses.append(current)
            continue

        dev_match = _DEV_LINE.match(line)
        if dev_match and current is not None:
            speed = _speed(dev_match.group("speed"))
            node = UsbNode(
                port=int(dev_match.group("port")),
                dev=int(dev_match.group("dev")),
                interface=int(dev_match.group("intf")),
                cls=dev_match.group("cls").strip(),
                driver=dev_match.group("driver").strip(),
                link_speed=speed,
            )
            current.nodes.append(node)
            if node.driver == adapter_driver:
                adapters.append(
                    AdapterLocation(
                        bus=current.bus,
                        controller=current.controller,
                        port=node.port,
                        dev=node.dev,
                        interface=node.interface,
                        link_speed=speed,
                        is_high_speed_usb2=speed == HIGH_SPEED_USB2_TOKEN,
                    )
                )

    # Sharing is decided on the bus (root-hub instance), not the driver string,
    # which is not unique across separate root hubs (see `UsbBus`).
    shared = None if len(adapters) < 2 else len({a.bus for a in adapters}) == 1
    all_hs = bool(adapters) and all(a.is_high_speed_usb2 for a in adapters)
    return TopologyReport(
        buses=tuple(buses),
        adapters=tuple(adapters),
        shared_controller=shared,
        all_high_speed_usb2=all_hs,
    )


def _speed(token: str | None) -> str | None:
    """Return a stripped link-speed token, or None when the field was absent."""
    if token is None:
        return None
    cleaned = token.strip()
    return cleaned or None
