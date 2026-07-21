"""Static-checker negative fixture: gravity torque flowing into an action target.

The AST checker (contracts.action.checker) must flag the construction of an
action target from a torque-named value — the audit-into-training leak 00 §8.3
forbids. This file is checker data; it is not imported or type-checked.
"""

from __future__ import annotations

from contracts.action import AcceptedPositionAction
from contracts.units import Nm


def build_action(gravity_torque: tuple[Nm, ...]) -> AcceptedPositionAction:
    """Sneak a gravity torque into the position action target."""
    return AcceptedPositionAction(values=gravity_torque)
