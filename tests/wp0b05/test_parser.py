"""The udevadm parser reads both axes from a dump, serial present or absent.

These run fully here: the parser is pure text-folding, and the deferred hardware
acceptances (②③④) reduce to running it on real captures once supplied.
"""

from __future__ import annotations

from pathlib import Path

from ops.hw.udev.model import AdapterAxisKind
from ops.hw.udev.parser import parse_udevadm_info

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "udevadm"


def test_serial_dump_yields_both_axes() -> None:
    """A serial-bearing dump gives dev_id, serial, port path, driver and type."""
    interface = parse_udevadm_info((_FIXTURES / "can0_serial.txt").read_text(encoding="utf-8"))
    assert interface.interface == "can0"
    assert interface.dev_id == "0x0"
    assert interface.serial == "OA_ADAPTER_A"
    assert interface.port_path == "1-1.2:1.0"
    assert interface.driver == "gs_usb"
    assert interface.arphrd_type == "280"


def test_two_channels_of_one_adapter_share_serial_differ_in_dev_id() -> None:
    """Adapter A's two channels share one serial and split on dev_id (FR-SYS-008)."""
    can0 = parse_udevadm_info((_FIXTURES / "can0_serial.txt").read_text(encoding="utf-8"))
    can1 = parse_udevadm_info((_FIXTURES / "can1_serial.txt").read_text(encoding="utf-8"))
    assert can0.serial == can1.serial == "OA_ADAPTER_A"
    assert can0.port_path == can1.port_path
    assert can0.dev_id != can1.dev_id


def test_no_serial_dump_leaves_serial_none_and_keeps_port_path() -> None:
    """A dump without ATTRS{serial} yields serial=None but a usable port-path fallback."""
    interface = parse_udevadm_info((_FIXTURES / "can0_noserial.txt").read_text(encoding="utf-8"))
    assert interface.serial is None
    assert interface.port_path == "1-1.2:1.0"
    assert interface.adapter_axis() is AdapterAxisKind.PORT_PATH
    assert interface.adapter_key() == "1-1.2:1.0"


def test_serial_dump_prefers_serial_axis() -> None:
    """When both are available, the adapter axis is serial, not port path."""
    interface = parse_udevadm_info((_FIXTURES / "can0_serial.txt").read_text(encoding="utf-8"))
    assert interface.adapter_axis() is AdapterAxisKind.SERIAL
    assert interface.adapter_key() == "OA_ADAPTER_A"
