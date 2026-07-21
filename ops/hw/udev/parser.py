"""Parser for `udevadm info -a -p /sys/class/net/<if>` output (`16` M-12 diagnostic).

`udevadm info -a` prints the device followed by its parent chain, one block per
level, deepest first. The two axes a fixed-name rule needs live at different
levels: `ATTR{dev_id}` and `ATTR{type}` on the net device itself, `ATTRS{serial}`
and the `KERNELS==` port path up on the USB nodes. This module folds one dump into
a single `UdevInterface`.

Reading a real capture is exactly what the deferred hardware acceptances (②③④)
become once a fixture is supplied, so the parser is written to the real format and
exercised on synthetic dumps here, never faking the measurement it enables.
"""

from __future__ import annotations

import re

from ops.hw.udev.model import UdevInterface

# A block header names the level being described; the first (non-parent) block is
# the net device, every later one is an ancestor.
_BLOCK_HEADER = re.compile(r"looking at (?:parent )?device '([^']*)':")
# `KERNEL==`, `DRIVER==`, `KERNELS==`, `DRIVERS==` — a bare match key and value.
_PLAIN_ATTR = re.compile(r'^\s*(KERNELS?|DRIVERS?|SUBSYSTEMS?)=="(.*)"\s*$')
# `ATTR{dev_id}=="0x0"` / `ATTRS{serial}=="..."` — a keyed attribute and value.
_KEYED_ATTR = re.compile(r'^\s*(ATTRS?)\{([^}]+)\}=="(.*)"\s*$')


class _Block:
    """One `looking at … device` block: its match keys and keyed attributes."""

    def __init__(self) -> None:
        self.kernel: str | None = None
        self.kernels: str | None = None
        self.driver: str | None = None
        self.drivers: str | None = None
        self.attr: dict[str, str] = {}
        self.attrs: dict[str, str] = {}


def _split_blocks(text: str) -> list[_Block]:
    """Split a udevadm dump into its device/parent blocks in walk order.

    Args:
        text: Raw `udevadm info -a` output.

    Returns:
        (list[_Block]) One block per level, device first, parents following.
    """
    blocks: list[_Block] = []
    current: _Block | None = None
    for line in text.splitlines():
        if _BLOCK_HEADER.search(line):
            current = _Block()
            blocks.append(current)
            continue
        if current is None:
            continue
        keyed = _KEYED_ATTR.match(line)
        if keyed:
            scope, name, value = keyed.group(1), keyed.group(2), keyed.group(3)
            (current.attr if scope == "ATTR" else current.attrs)[name] = value
            continue
        plain = _PLAIN_ATTR.match(line)
        if plain:
            key, value = plain.group(1), plain.group(2)
            _assign_plain(current, key, value)
    return blocks


def _assign_plain(block: _Block, key: str, value: str) -> None:
    """Store a bare match-key value on a block.

    Args:
        block: Block being filled.
        key: One of `KERNEL`, `KERNELS`, `DRIVER`, `DRIVERS`, `SUBSYSTEM(S)`.
        value: Quoted value already unwrapped.
    """
    if key == "KERNEL":
        block.kernel = value
    elif key == "KERNELS":
        block.kernels = value
    elif key == "DRIVER":
        block.driver = value
    elif key == "DRIVERS":
        block.drivers = value


def parse_udevadm_info(text: str) -> UdevInterface:
    """Fold one `udevadm info -a` dump into a single interface record.

    The channel axis (`dev_id`, `type`) is read from the net-device block; the
    adapter axis (`serial`, port path, driver) is read from the first ancestor
    that actually declares a `DRIVERS` — the USB-interface node that carries
    `gs_usb`. Serial is taken from the first ancestor that exposes `ATTRS{serial}`,
    which sits one level further up on the USB device node.

    Args:
        text: Raw dump for exactly one interface.

    Returns:
        (UdevInterface) The folded record.

    Raises:
        ValueError: If the dump contains no device block at all.
    """
    blocks = _split_blocks(text)
    if not blocks:
        raise ValueError("no udev device block found in dump")

    device = blocks[0]
    interface = device.kernel or ""
    dev_id = device.attr.get("dev_id")
    arphrd_type = device.attr.get("type")

    driver: str | None = None
    port_path: str | None = None
    for block in blocks[1:]:
        if block.drivers:
            driver = block.drivers
            port_path = block.kernels
            break

    serial: str | None = None
    for block in blocks[1:]:
        if "serial" in block.attrs:
            serial = block.attrs["serial"]
            break

    return UdevInterface(
        interface=interface,
        dev_id=dev_id,
        serial=serial,
        port_path=port_path,
        driver=driver,
        arphrd_type=arphrd_type,
    )
