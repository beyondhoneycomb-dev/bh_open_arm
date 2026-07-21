"""Canonical-path fixture: `from openarm_driver import …` form of the banned import.

Proves the scan bites the from-import form too (acceptance ③).
"""

from __future__ import annotations

from openarm_driver import DamiaoMotorsBus


def make_bus(channel: str) -> DamiaoMotorsBus:
    """Construct the driver's own CAN bus via a from-import."""
    return DamiaoMotorsBus(channel)
