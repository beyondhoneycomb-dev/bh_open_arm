"""Acceptance 6: a physical quantity may not be born as a bare float.

Declaring a torque as a raw `float` where the `Nm` tag type is required is a static
type error — a quantity carries its unit in its type, not in a comment. Expected
error code: [assignment].
"""

from __future__ import annotations

from contracts.units import Nm

joint_torque: Nm = 5.0
