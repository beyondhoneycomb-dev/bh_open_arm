"""Shared value types for udev fixed-name binding (`01` FR-SYS-008, `02` FR-CON-005).

Two facts of the hardware fix the shape of everything downstream and are worth
stating once, here, where the types live:

- The kernel stamps a distinct `dev_id` on each channel netdev of one adapter
  (`gs_usb.c:1355` `netdev->dev_id = channel`), so `dev_id` is the *channel* axis.
- Both channels of one adapter walk up to the *same* USB device, so they report
  the same `ATTRS{serial}` and the same USB port path — the adapter axis is shared
  per adapter and cannot, alone, tell the two channels apart.

A udev rule that binds a fixed name must therefore constrain both axes at once
(FR-SYS-008). These types carry exactly the fields those two axes are read from.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class AdapterAxisKind(enum.Enum):
    """Which attribute discriminates the adapter in a two-axis rule.

    `SERIAL` binds `ATTRS{serial}`; `PORT_PATH` binds `KERNELS==` (the USB port
    path). Port-path is the fallback the spec mandates when the adapter reports no
    iSerial (`16` M-12). The distinction is not cosmetic — it changes what a rule
    means when the adapter is moved to another physical port (see `port_swap_stable`).
    """

    SERIAL = "serial"
    PORT_PATH = "port_path"

    @property
    def udev_key(self) -> str:
        """Return the udev match key this axis renders as.

        Returns:
            (str) `ATTRS{serial}` or `KERNELS`.
        """
        return "ATTRS{serial}" if self is AdapterAxisKind.SERIAL else "KERNELS"

    @property
    def port_swap_stable(self) -> bool:
        """Whether a name bound on this axis survives moving the adapter to another port.

        A serial-axis rule follows the adapter across ports (name stays put); a
        port-path-axis rule is nailed to the physical USB port (name moves to
        whatever adapter now occupies that port). Acceptance ⑥ requires this be
        documented, not assumed — this property is that documentation, in code.

        Returns:
            (bool) True for `SERIAL`, False for `PORT_PATH`.
        """
        return self is AdapterAxisKind.SERIAL


@dataclass(frozen=True)
class UdevInterface:
    """One CAN net interface as `udevadm info -a -p /sys/class/net/<if>` describes it.

    Attributes:
        interface: Kernel name at capture time (`can0`). Non-deterministic across
            boots (`16` M-12) — kept only to key a measurement, never to assign a role.
        dev_id: `ATTR{dev_id}` of the interface's own device — the per-channel
            discriminator (`0x0`/`0x1` within one adapter), or None if absent.
        serial: `ATTRS{serial}` (USB iSerial) of the adapter, or None when the
            adapter reports none. Shared by both channels of one adapter.
        port_path: `KERNELS==` USB port-path token of the adapter's interface node
            (`1-1.2:1.0`), the fallback adapter discriminator, or None if absent.
        driver: `DRIVERS==` of the adapter interface node (`gs_usb`), or None.
        arphrd_type: `ATTR{type}` — `280` (ARPHRD_CAN) for a CAN link, or None.
    """

    interface: str
    dev_id: str | None
    serial: str | None
    port_path: str | None
    driver: str | None
    arphrd_type: str | None

    def adapter_key(self) -> str | None:
        """Return the value that identifies this interface's adapter.

        Serial wins when present; otherwise the USB port path is the fallback key
        (`16` M-12). None means neither axis is available — an interface that cannot
        be pinned by any adapter discriminator.

        Returns:
            (str | None) Serial, else port path, else None.
        """
        if self.serial is not None:
            return self.serial
        return self.port_path

    def adapter_axis(self) -> AdapterAxisKind | None:
        """Return which adapter axis this interface would be bound on.

        Returns:
            (AdapterAxisKind | None) `SERIAL` if a serial is present, else
            `PORT_PATH` if a port path is present, else None.
        """
        if self.serial is not None:
            return AdapterAxisKind.SERIAL
        if self.port_path is not None:
            return AdapterAxisKind.PORT_PATH
        return None
