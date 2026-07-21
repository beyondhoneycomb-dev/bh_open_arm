"""Positive control: correct CTR-ACT usage must PASS mypy --strict.

If this fails, the sibling type-error fixtures are just "mypy always fails here"
rather than distinguishing wrong from right.
"""

from __future__ import annotations

from contracts.action import AcceptedPositionAction, ExecutedMitCommand, RequestedPositionAction
from contracts.units import Deg, Nm, Rad, RadPerSec

positions = tuple(Deg(0.0) for _ in range(16))
requested = RequestedPositionAction(values=positions)
accepted = AcceptedPositionAction(values=positions)
mit = ExecutedMitCommand(kp=1.0, kd=1.0, q=Rad(0.0), dq=RadPerSec(0.0), tau=Nm(0.0))

evidence: tuple[RequestedPositionAction, AcceptedPositionAction, ExecutedMitCommand] = (
    requested,
    accepted,
    mit,
)
