"""Canonical-path fixture: imports the permitted `openarm_control` (IK/FK, no CAN).

FR-SYS-010 allows it; the scan must NOT flag it (acceptance ④, over-block guard).
"""

from __future__ import annotations

import openarm_control


def kinematics() -> object:
    """Return the control package's kinematics entry point — no CAN involved."""
    return openarm_control.Kinematics
