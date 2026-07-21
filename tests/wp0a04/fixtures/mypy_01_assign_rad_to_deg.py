"""Acceptance 1: a tag type is a real distinct type, not an alias.

Assigning a `Rad` where a `Deg` is expected must be a static type error, caught by
mypy, not a runtime check. Expected error code: [assignment].
"""

from __future__ import annotations

from contracts.units import Deg, Rad

wrong_angle: Deg = Rad(1.0)
