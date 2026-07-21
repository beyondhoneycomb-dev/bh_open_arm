"""Parser for `ethtool -i <if>` output (`01` FR-SYS-008 acceptance ①, `16` M-12).

Acceptance ① requires confirming the adapter binds an in-tree kernel driver
(`gs_usb` family), recording the *real* output. The live `ethtool -i` call needs a
physical adapter and is deferred; the driver line it prints has a fixed shape, so the
parser is written to that shape and exercised on a synthetic fixture here. The reverify
hook runs this same parser against a real capture when one is supplied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# `01` FR-SYS-008 / `16` M-12 — the Pibiger SavvyCAN-FD-X2 binds the in-tree `gs_usb`
# driver. Acceptance ① confirms membership in this family against real output.
IN_TREE_DRIVER_FAMILY = frozenset({"gs_usb"})

_FIELD = re.compile(r"^(driver|version|firmware-version|bus-info):\s*(.*)$")


@dataclass(frozen=True)
class DriverReport:
    """The fields of one `ethtool -i` block.

    Attributes:
        driver: `driver:` field (`gs_usb`).
        version: `version:` field, or None if absent.
        firmware_version: `firmware-version:` field, or None if absent.
        bus_info: `bus-info:` field (the USB port path), or None if absent.
    """

    driver: str
    version: str | None
    firmware_version: str | None
    bus_info: str | None


def parse_ethtool_i(text: str) -> DriverReport:
    """Parse `ethtool -i` output into a driver report.

    Args:
        text: Raw `ethtool -i <if>` output.

    Returns:
        (DriverReport) The parsed fields.

    Raises:
        ValueError: If no `driver:` line is present.
    """
    fields: dict[str, str] = {}
    for line in text.splitlines():
        match = _FIELD.match(line.strip())
        if match:
            fields[match.group(1)] = match.group(2).strip()
    if "driver" not in fields:
        raise ValueError("ethtool -i output has no driver: line")
    return DriverReport(
        driver=fields["driver"],
        version=fields.get("version"),
        firmware_version=fields.get("firmware-version"),
        bus_info=fields.get("bus-info"),
    )


def is_in_tree_driver(report: DriverReport) -> bool:
    """Whether the report's driver is an in-tree `gs_usb`-family driver (acceptance ①).

    Args:
        report: A parsed driver report.

    Returns:
        (bool) True iff the driver is in the in-tree family.
    """
    return report.driver in IN_TREE_DRIVER_FAMILY
