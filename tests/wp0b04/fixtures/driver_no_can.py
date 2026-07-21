"""Synthetic driver-shaped source that opens no CAN socket.

Stands in for a CAN-free package (the shape M-24 records for `openarm_control` /
`openarm_ker`). The audit must judge `opens_can=False` (acceptance ②) — the scan
does not answer "yes" to everything. Read as text only.
"""

from __future__ import annotations


def clamp(value: float, low: float, high: float) -> float:
    """Pure numeric helper — no socket, no interface, no CAN."""
    return max(low, min(high, value))
