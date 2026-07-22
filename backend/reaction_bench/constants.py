"""Named constants for the WP-2C-06 reaction-time measurement bench.

Every value here is an identifier, a segment name, or a labelled reference — never a
measured pass line. This bench measures the detection-confirm-to-first-reaction-frame
latency and *records its distribution*, but it decides no target: NFR-SAF-002 (~1/K,
K=90 -> <=15 ms), NFR-SAF-003 (<=2 CAN cycles) and NFR-SAF-004 (<=10 ms) are all
decision-needed (`02b` WP-2C-06 acceptance 2), so their provisional figures are carried
into the evidence as labelled references only, never compared. The numeric pass line is
fixed after measurement by a regression gate, not before it (`00` invariant I-6).
"""

from __future__ import annotations

from typing import Any

# The gate this bench renders evidence toward. WP-2C-06 is a *downstream consumer* of
# PG-SAFE-001 (`03` §5.11 torque-ON WP binding), not its owner, so the gate name is
# imported from the WP-1-05 producer rather than restated: one definition, no drift.
from backend.torque_bringup.constants import PG_SAFE_001

WP_ID = "WP-2C-06"
GATE = PG_SAFE_001

# Environment variable a caller sets to point the re-verification hook at a directory of
# real reaction-time captures (`02a` §4.1). Until it is set, the real on-rig measurement is
# skipped with a reason rather than asserted green — a reaction time is never faked, since
# it needs torque-ON plus a trusted clock correlating the confirm event to the CAN frame's
# first byte, neither of which exists on this host (THE ONE RULE).
FIXTURE_ENV_VAR = "OPENARM_REACTION_BENCH_REAL_FIXTURE"

# The three decision-needed reaction-time targets, carried into the evidence as labelled
# references and never compared. `02b` WP-2C-06 acceptance 2 forbids nailing any of them
# before measurement; they exist here so an artifact records *which* undecided figures a
# future regression gate will fix, not so the bench can judge against them. The status
# marker echoed in the values is the plan's own decision-needed token, kept as data.
REFERENCE_TARGETS_DECISION_NEEDED: tuple[dict[str, Any], ...] = (
    {"req": "NFR-SAF-002", "provisional": "~1/K (K=90 -> <=15 ms)", "status": "[결정필요]"},
    {"req": "NFR-SAF-003", "provisional": "<=2 CAN cycles", "status": "[결정필요]"},
    {"req": "NFR-SAF-004", "provisional": "<=10 ms", "status": "[결정필요]"},
)

REFERENCE_NOTE = (
    "NFR-SAF-002/003/004 are all [결정필요]; they are recorded here as references only and "
    "this bench renders no pass/fail on the reaction time — the pass line is fixed after "
    "measurement by a regression gate (02b WP-2C-06 acceptance 2, 00 invariant I-6)"
)
