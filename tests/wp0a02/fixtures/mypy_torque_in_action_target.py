"""Acceptance 4: a torque (Nm) in a position action target is a static type error.

`acceptedPositionAction` is position-only in `Deg`; handing it `Nm` does not
type-check. Expected error code: [arg-type].
"""

from __future__ import annotations

from contracts.action import AcceptedPositionAction
from contracts.units import Nm

leaked = AcceptedPositionAction(values=(Nm(1.0),))
