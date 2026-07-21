"""Canonical-path fixture: imports the permitted `openarm_ker` (USB, no CAN).

FR-SYS-010 allows it; the scan must NOT flag it (acceptance ④, over-block guard).
"""

from __future__ import annotations

import openarm_ker


def open_usb(port: str) -> object:
    """Open the USB transport — a permitted path that opens no CAN socket."""
    return openarm_ker.open(port)
