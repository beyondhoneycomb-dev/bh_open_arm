"""Canonical-path fixture: statically imports the banned `openarm_driver`.

Proves `find_banned_driver_import` bites the plain-import form (acceptance ③).
Read as text by the scan; never imported at runtime.
"""

from __future__ import annotations

import openarm_driver


def make_bus(channel: str) -> object:
    """Construct the driver's own CAN bus — the forbidden second binder."""
    return openarm_driver.DamiaoMotorsBus(channel)
