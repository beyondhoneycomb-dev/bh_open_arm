"""Canonical-path fixture: a permitted import alongside the banned one.

Proves the scan flags exactly the banned import and leaves the allowed one alone
(acceptance ④) — one finding, not two.
"""

from __future__ import annotations

import openarm_control
import openarm_driver


def make() -> tuple[object, object]:
    """Reference both packages so neither import is unused."""
    return (openarm_control.Kinematics, openarm_driver.DamiaoMotorsBus)
