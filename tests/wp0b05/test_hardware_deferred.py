"""Honestly-deferred hardware acceptances (①②③⑤⑥) — skipped-with-reason, never faked.

None of these can pass on a dev desktop with no CAN adapters. Each is guarded by a real
probe of `/sys/class/net`, so on a rig with two gs_usb adapters they run against live
output, and here they skip with the reason and a pointer to the re-verification hook that
carries the same check to a real capture (plan 02a §4.1).

The THE-ONE-RULE consequence: a hardware green that cannot be produced here is skipped,
not asserted. The synthetic-fixture tests in the sibling files prove the code is correct;
these prove the deferral is explicit.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ops.hw.udev.determinism import REQUIRED_REBOOT_CYCLES
from ops.hw.udev.ethtool import is_in_tree_driver, parse_ethtool_i
from ops.hw.udev.measurement import (
    build_measurement_table,
    dev_id_distinguishes_channels,
    serial_shared_per_adapter,
)
from ops.hw.udev.parser import parse_udevadm_info

# ARPHRD_CAN, as `/sys/class/net/<if>/type` reports it for a CAN link.
_CAN_TYPE = "280"
_IN_TREE_DRIVER = "gs_usb"
_NET_ROOT = Path("/sys/class/net")
# Two adapters x two channels — the rig this WP's hardware acceptances assume.
_REQUIRED_CHANNELS = 4


def _gs_usb_can_interfaces() -> list[str]:
    """Return CAN interfaces currently bound to the in-tree gs_usb driver.

    Reads sysfs directly so the probe needs no CAN tooling installed. Absent or
    unreadable sysfs yields an empty list — the honest "no hardware" answer.

    Returns:
        (list[str]) Interface names, sorted.
    """
    if not _NET_ROOT.is_dir():
        return []
    found: list[str] = []
    for entry in sorted(_NET_ROOT.iterdir()):
        type_file = entry / "type"
        driver_link = entry / "device" / "driver"
        try:
            is_can = type_file.read_text(encoding="utf-8").strip() == _CAN_TYPE
        except OSError:
            continue
        if is_can and driver_link.is_symlink() and driver_link.resolve().name == _IN_TREE_DRIVER:
            found.append(entry.name)
    return found


def _two_adapters_present() -> bool:
    """Whether at least a two-adapter (four-channel) gs_usb rig is attached.

    Returns:
        (bool) True iff four or more gs_usb CAN channels are present.
    """
    return len(_gs_usb_can_interfaces()) >= _REQUIRED_CHANNELS


_NO_RIG_REASON = (
    "requires two physical gs_usb CAN adapters (four channels); none attached on this host. "
    "Supply a real capture to ops.hw.udev.reverify.reverify_from_fixture to re-verify."
)


@pytest.mark.skipif(not _two_adapters_present(), reason=_NO_RIG_REASON)
def test_live_ethtool_reports_in_tree_gs_usb() -> None:
    """Acceptance ①: `ethtool -i` on each real interface confirms the in-tree driver."""
    for interface in _gs_usb_can_interfaces():
        output = subprocess.run(
            ["ethtool", "-i", interface],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert is_in_tree_driver(parse_ethtool_i(output))


@pytest.mark.skipif(not _two_adapters_present(), reason=_NO_RIG_REASON)
def test_live_serial_is_shared_per_adapter() -> None:
    """Acceptance ②: measured on real udevadm output, serial is shared per adapter."""
    interfaces = tuple(
        parse_udevadm_info(
            subprocess.run(
                ["udevadm", "info", "-a", "-p", f"/sys/class/net/{name}"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        )
        for name in _gs_usb_can_interfaces()
    )
    assert serial_shared_per_adapter(build_measurement_table(interfaces))


@pytest.mark.skipif(not _two_adapters_present(), reason=_NO_RIG_REASON)
def test_live_dev_id_distinguishes_channels() -> None:
    """Acceptance ③: measured on real udevadm output, dev_id splits the channels."""
    interfaces = tuple(
        parse_udevadm_info(
            subprocess.run(
                ["udevadm", "info", "-a", "-p", f"/sys/class/net/{name}"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        )
        for name in _gs_usb_can_interfaces()
    )
    assert dev_id_distinguishes_channels(build_measurement_table(interfaces))


@pytest.mark.skip(
    reason=(
        f"acceptance ⑤ requires {REQUIRED_REBOOT_CYCLES} real reboots — impossible in-process. "
        "Capture one binding per boot into reboots.json and re-verify via "
        "ops.hw.udev.reverify.reverify_from_fixture (evaluator proven in test_determinism)."
    )
)
def test_reboot_determinism_ten_cycles() -> None:
    """Acceptance ⑤: ten reboots bind the four names to the same physical channels."""
    raise AssertionError("unreachable: captured out-of-process, then re-verified via the hook")


@pytest.mark.skip(
    reason=(
        "acceptance ⑥ requires a physical port swap plus reboot. Serial-axis rules keep the "
        "name across ports; port-path-axis rules move it (documented on AdapterAxisKind."
        "port_swap_stable). Re-verify the observed behavior via the reverify hook."
    )
)
def test_port_swap_behavior_matches_axis_choice() -> None:
    """Acceptance ⑥: after a port swap, names behave per the chosen adapter axis."""
    raise AssertionError("unreachable: captured out-of-process, then re-verified via the hook")
