"""Sim mode tiers and the dry-run hard block (WP-0C-09, safety-critical).

The three mutually exclusive sim modes on the shared Robot ABC — pure-sim (a),
digital-twin (b, read-only mirror), dry-run (c) — all CAN-not-opened, plus the
dry-run's six checks (`09` FR-SIM-030) and the real-transmission hard block
(`09` FR-SIM-033) that is the whole point of putting dry-run in Wave 0-C: it is a
safety gate, the prerequisite for Wave 2D manual and 3C teleop, not a convenience.

The wiring of the hard gate *into* the pre-transmission path before Wave 2D is
owned by `02b`, not here; this package builds the implementation, the six checkers,
the violation reporter, and the interlock.
"""

from __future__ import annotations

from sim.dryrun.canon import ClampCanon, PositionCanon, VelocityCanon
from sim.dryrun.interlock import (
    HardBlockError,
    ModalConfirmation,
    TransmissionGrant,
    authorize_transmission,
    authorize_with_modal_confirm,
)
from sim.dryrun.modes import ModeController, ModeExclusionError, SimMode
from sim.dryrun.runner import DryRunRunner, Waypoint
from sim.dryrun.violation import DryRunCheck, DryRunVerdict, Violation

__all__ = [
    "ClampCanon",
    "PositionCanon",
    "VelocityCanon",
    "HardBlockError",
    "ModalConfirmation",
    "TransmissionGrant",
    "authorize_transmission",
    "authorize_with_modal_confirm",
    "ModeController",
    "ModeExclusionError",
    "SimMode",
    "DryRunRunner",
    "Waypoint",
    "DryRunCheck",
    "DryRunVerdict",
    "Violation",
]
