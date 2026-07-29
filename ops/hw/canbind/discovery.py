"""Enumerate the CAN channels this host exposes, without renaming anything.

WP-0B-05's job is a stable identity for each arm's CAN channel. udev rules were the first
mechanism: rename `canN` to a fixed name and let downstream bind to the name. This module is
the second mechanism — enumerate the channels as the kernel already named them and identify
each by a key that outlives a reboot, so nothing needs root, nothing is written to `/etc`, and
`canN` renumbering stops mattering because nothing binds to `canN`.

The key is `(ID_PATH, dev_id)`:

  * `ID_PATH` is the physical USB/PCI position udev derives, identical for every channel of a
    multi-channel adapter (`pci-0000:80:14.0-usb-0:10.3.1.2:1.0` for both channels of a
    PCAN-USB Pro FD).
  * `dev_id` is the channel index within that adapter (`0x0`, `0x1`), which is what separates
    the two. Neither axis alone is enough; a two-channel adapter collapses on `ID_PATH` and two
    identical adapters collapse on `dev_id`.

What this key does NOT survive is moving the adapter to a different USB port — `ID_PATH` is a
position, not a serial number. That is reported as a changed key rather than silently rebound,
because a silent rebind is how the left arm becomes the right one.

`03` §2.1 is the reason identification cannot stop here: both arms answer on send `0x01–0x08`
and recv `0x11–0x18`, so **a bus scan cannot tell left from right** — the spec records that
three upstream projects disagree about which channel is which. Enumeration finds channels and
counts motors; deciding which arm is on which channel is `identify.py`'s problem and needs the
operator to move an arm.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from backend.can.link.parser import LinkState, UnrecognizedLinkFormatError, parse_link_show
from ops.hw.udev.rules import ARPHRD_CAN_TYPE

# Where the kernel exposes network interfaces. A parameter on the scan functions rather than a
# constant baked into them, so the tests drive a fixture tree instead of this host.
SYS_CLASS_NET = Path("/sys/class/net")

# The sysfs attribute that separates channels of one multi-channel adapter.
DEV_ID_ATTR = "dev_id"

# udev property naming the physical position of the adapter.
ID_PATH_PROPERTY = "ID_PATH"

# What actually marks a CAN interface in sysfs. Measured on this bench rather than assumed:
# `can0/type` reads 280 (ARPHRD_CAN) while ethernet reads 1 and loopback 772. The `can_*`
# bittiming attributes are netlink, not sysfs — they appear in `ip -details link show` and in no
# file, so keying on one of those names finds nothing on a real host.
TYPE_ATTR = "type"

_ID_PATH_LINE = re.compile(r"^ID_PATH=(?P<value>.+)$", re.MULTILINE)
_UDEVADM_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class CanChannel:
    """One CAN channel the host exposes, with the identity that outlives a reboot.

    Attributes:
        interface: The kernel's current name (`can0`). Unstable across replug by design —
            carried so a caller can open a socket, never so a caller can identify a channel.
        id_path: The udev physical position, shared by every channel of one adapter.
        dev_id: The channel index within the adapter, as the raw sysfs string (`0x1`).
        driver: The kernel module bound to it (`peak_usb`), or empty when unreadable.
        state: The CAN link state (`STOPPED` before bring-up, `ERROR-ACTIVE` when up).
        bitrate_bps: Arbitration bitrate, or None before bring-up sets one.
    """

    interface: str
    id_path: str
    dev_id: str
    driver: str
    state: str
    bitrate_bps: int | None

    @property
    def channel_key(self) -> str:
        """The reboot-stable identity: physical position plus channel index.

        A missing axis becomes an explicit `?` rather than an empty string, so two channels that
        each fail to report the same axis do not collapse onto one key and read as one channel.
        """
        return f"{self.id_path or '?'}/dev_id:{self.dev_id or '?'}"

    @property
    def is_up(self) -> bool:
        """Whether the link is running; a STOPPED channel accepts no traffic."""
        return self.state not in ("", "STOPPED")


def list_can_channels(sys_class_net: Path = SYS_CLASS_NET) -> list[CanChannel]:
    """Return every CAN channel on the host, sorted by its stable key.

    Args:
        sys_class_net: The `/sys/class/net` directory to read; overridden by tests.

    Returns:
        (list[CanChannel]) One entry per channel, empty when the host has no CAN adapter.
            Sorted by `channel_key` so the order does not follow kernel enumeration.
    """
    if not sys_class_net.is_dir():
        return []
    channels = [
        _read_channel(entry, _link_state_for(entry.name))
        for entry in sorted(sys_class_net.iterdir())
        if _is_can_interface(entry)
    ]
    return sorted(channels, key=lambda channel: channel.channel_key)


def _is_can_interface(entry: Path) -> bool:
    """Report whether a `/sys/class/net` entry is a CAN interface.

    Keys on ARPHRD type rather than on a name prefix: a renamed interface is still CAN, and an
    ethernet device called `can_backup` is not.
    """
    return _read_attr(entry / TYPE_ATTR) == ARPHRD_CAN_TYPE


def _read_channel(entry: Path, link: LinkState | None) -> CanChannel:
    """Build one channel record from its sysfs directory plus its parsed link state."""
    name = entry.name
    return CanChannel(
        interface=name,
        id_path=_id_path_for(name),
        dev_id=_read_attr(entry / DEV_ID_ATTR),
        driver=_driver_for(entry),
        state=link.state.upper() if link else "",
        bitrate_bps=link.bitrate if link else None,
    )


def _read_attr(path: Path) -> str:
    """Return a sysfs attribute stripped, or empty when it cannot be read."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _read_int(path: Path) -> int | None:
    """Return a sysfs attribute as an int, or None when absent or non-numeric."""
    raw = _read_attr(path)
    try:
        return int(raw)
    except ValueError:
        return None


def _driver_for(entry: Path) -> str:
    """Return the module name bound to the interface, or empty when unresolvable."""
    try:
        return (entry / "device" / "driver").resolve().name
    except OSError:
        return ""


def _id_path_for(interface: str) -> str:
    """Return udev's `ID_PATH` for an interface, or empty when udev cannot answer.

    Shelling out to `udevadm` rather than deriving the path from `DEVPATH` ourselves: the
    derivation rules are udev's and they change with its version, so a reimplementation would
    disagree with the system that actually names things.
    """
    try:
        completed = subprocess.run(  # noqa: S603 — fixed argv, no shell, no user input
            ["udevadm", "info", "-q", "property", "-p", f"/sys/class/net/{interface}"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=_UDEVADM_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if completed.returncode != 0:
        return ""
    match = _ID_PATH_LINE.search(completed.stdout)
    return match.group("value").strip() if match else ""


def _link_state_for(interface: str) -> LinkState | None:
    """Return the parsed `ip -details link show` state, or None when it cannot be read.

    State and bitrate live in netlink, not sysfs, so this is the only place they come from.
    WP-0B-02's parser is reused rather than re-implemented: a second reader of the same text
    would drift from the one the link-verification gate judges against.
    """
    try:
        completed = subprocess.run(  # noqa: S603 — fixed argv, no shell
            ["ip", "-details", "link", "show", interface],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=_UDEVADM_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    try:
        return parse_link_show(completed.stdout, interface)
    except UnrecognizedLinkFormatError:
        return None


def bring_up_command(interface: str, bitrate_bps: int, data_bitrate_bps: int) -> list[str]:
    """Return the argv that brings a CAN-FD channel up, for an operator to run.

    This module never runs it. Bring-up needs `CAP_NET_ADMIN`, and a tool that silently
    escalates is a tool nobody can audit; the caller shows the command and the operator runs it.

    Args:
        interface: The kernel interface name to bring up.
        bitrate_bps: Arbitration-phase bitrate.
        data_bitrate_bps: Data-phase bitrate for the FD frames.

    Returns:
        (list[str]) The argv, ready to render with `shlex.join`.
    """
    return [
        "sudo",
        "ip",
        "link",
        "set",
        interface,
        "up",
        "type",
        "can",
        "bitrate",
        str(bitrate_bps),
        "dbitrate",
        str(data_bitrate_bps),
        "fd",
        "on",
    ]
