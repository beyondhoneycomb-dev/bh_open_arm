"""Static-checker positive fixture: a clean position action target.

Constructing the action target from position degrees must NOT be flagged, proving
the checker rejects only torque, not honest position values.
"""

from __future__ import annotations

from contracts.action import AcceptedPositionAction
from contracts.units import Deg


def build_action(positions: tuple[Deg, ...]) -> AcceptedPositionAction:
    """Build the position action target from degree positions."""
    return AcceptedPositionAction(values=positions)
