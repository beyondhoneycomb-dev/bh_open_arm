"""Numeric Move-to (WP-2D-09) — check first, execute only on pass.

A typed joint or EE target is admitted only after a limit check (WP-2A-03's
``JogClampPath``) and, for an EE pose, an IK-solution-existence check (WP-2D-01's
``CartesianJog``). The gate has a single guarded execution site, so a move that skips
the checks cannot be expressed (FR-MAN-015, acceptance ①); the report shows every
refusal per reason (acceptance ②).

Public surface:

- ``NumericMoveTo`` / ``build_numeric_move_to`` — the gate.
- ``JointMoveTo`` / ``PoseMoveTo`` — the two numeric inputs.
- ``MoveToCheckReport`` / ``MoveToResult`` and the finding types — the per-reason output.
- ``move_to_limits_from_soft_limits`` — assemble the position envelope from the
  soft-limit truth for the clamp the gate consumes.
"""

from __future__ import annotations

from backend.moveto.gate import NumericMoveTo, build_numeric_move_to
from backend.moveto.limits import move_to_limits_from_soft_limits, soft_limit_mechanical_deg
from backend.moveto.report import (
    IkExistenceFinding,
    LimitFinding,
    MoveToCheckReport,
    MoveToResult,
)
from backend.moveto.request import JointMoveTo, PoseMoveTo

__all__ = [
    "IkExistenceFinding",
    "JointMoveTo",
    "LimitFinding",
    "MoveToCheckReport",
    "MoveToResult",
    "NumericMoveTo",
    "PoseMoveTo",
    "build_numeric_move_to",
    "move_to_limits_from_soft_limits",
    "soft_limit_mechanical_deg",
]
