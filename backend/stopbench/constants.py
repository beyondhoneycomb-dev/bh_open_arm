"""Named constants for the WP-2A-06 stop-path latency regression bench.

Every value here is an identifier, a segment name, or a reused reference — never a
measured pass line. This bench re-measures the deadman-release-to-CAN-hold-frame path
under the Wave 2A configuration and *decomposes* it, but it decides no target: `04`
NFR-MAN-002's 20 ms is `[unconfirmed]` and WP-2A-06 acceptance ② forbids nailing it, so
the reference target is imported from the WP-1-05 producer and carried for reference
only, never redefined and never compared.
"""

from __future__ import annotations

# The WP-1-05 gate this bench re-measures under the 2A configuration. Imported from the
# producer so the gate name has one definition; WP-2A-06 consumes PG-STOP-001, it does
# not own it (`03` §5.7 WP binding).
from backend.torque_bringup.constants import PG_STOP_001, STOP_LATENCY_TARGET_MS

WP_ID = "WP-2A-06"
GATE = PG_STOP_001

# The `[unconfirmed]` NFR-MAN-002 target, carried into the evidence as a labelled
# reference only. Reused from WP-1-05 rather than re-stated, so the one number the plan
# forbids nailing has exactly one home and cannot drift to a second value here.
REFERENCE_TARGET_MS_UNCONFIRMED = STOP_LATENCY_TARGET_MS

# Environment variable a caller sets to point the re-verification hook at a directory of
# real stop-path captures (`02a` §4.1). Until it is set, the real on-rig measurement is
# skipped with a reason rather than asserted green — the stop-latency number is never
# faked, since it needs rig torque-ON plus the kernel-clock instrumentation `03` §5.7.0
# demands, neither of which exists on this host.
FIXTURE_ENV_VAR = "OPENARM_STOPBENCH_REAL_FIXTURE"
