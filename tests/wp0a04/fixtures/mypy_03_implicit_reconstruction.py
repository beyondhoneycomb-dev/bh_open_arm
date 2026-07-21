"""Acceptance 3: no implicit conversion, including via a constructor.

Reconstructing a `Rad` directly from a `Deg` object — hoping the wrapper is just a
number — is a static type error, because the constructor takes a `float`, not a
foreign tag type. Crossing units requires a named conversion. Expected error
code: [arg-type].
"""

from __future__ import annotations

from contracts.units import Deg, Rad

reinterpreted = Rad(Deg(1.0))
