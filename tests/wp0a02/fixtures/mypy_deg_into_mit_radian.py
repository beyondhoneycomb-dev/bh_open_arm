"""Acceptance 4: a degree angle where the MIT command expects radians is a type error.

`executedMitCommand.q` is `Rad` (12 §2.7 CAN boundary); a `Deg` there does not
type-check. Expected error code: [arg-type].
"""

from __future__ import annotations

from contracts.action import ExecutedMitCommand
from contracts.units import Deg, Nm, RadPerSec

wrong = ExecutedMitCommand(kp=1.0, kd=1.0, q=Deg(0.0), dq=RadPerSec(0.0), tau=Nm(0.0))
