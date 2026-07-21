"""Violation fixture: a process spawn that configures a CAN link.

Proves `staticcheck.find_link_set_calls` bites — `01` FR-SYS-006 forbids code from
setting the link, and an actual `ip link set` exec is exactly the forbidden shape
(acceptance ⑤). The scan must flag it.
"""

from __future__ import annotations

import subprocess


def bring_up(iface: str) -> None:
    """Configure and raise a CAN link — the forbidden shape."""
    subprocess.run(
        ["sudo", "ip", "link", "set", iface, "type", "can", "bitrate", "1000000", "fd", "on"],
        check=True,
    )
