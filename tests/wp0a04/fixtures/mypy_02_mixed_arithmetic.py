"""Acceptance 2: mixed-unit arithmetic is a static type error.

`Deg + Rad` has no overload — same-unit addition is the only sanctioned form — so
mixing them does not type-check. Expected error code: [operator].
"""

from __future__ import annotations

from contracts.units import Deg, Rad

mixed = Deg(1.0) + Rad(1.0)
