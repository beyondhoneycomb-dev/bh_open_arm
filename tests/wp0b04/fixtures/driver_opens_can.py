"""Synthetic `openarm_driver`-shaped source that opens a CAN socket.

Stands in for the real `driver.py` the M-24 audit cannot read on this host. The
audit must judge `opens_can=True` and cite the evidence lines (acceptance ②).
Read as text only; never imported.
"""

from __future__ import annotations

import can
from openarm_can import CANSocket


def open_bus(channel: str) -> CANSocket:
    """Open the driver's own CAN socket — the in-process double bind M-24 asks about."""
    bus = can.interface.Bus(channel=channel, interface="socketcan")
    return CANSocket(bus)
