"""Named constants for the guarded torque-ON bring-up (WP-1-05).

Every value here is a spec-given identifier, gate name, or provenance label — never a
measured pass line. The one numeric latency figure recorded, `STOP_LATENCY_TARGET_MS`,
is the `[unconfirmed]` target of `04` NFR-MAN-002: it is carried into the evidence as a
*reference* and is never compared against a measurement, because acceptance ⑬ forbids
nailing a numeric target — the measured P99 is canon and the rig confirms it.
"""

from __future__ import annotations

# The gates this WP gates on (`03` gate table, `02a` §8): PG-SAFE-001 and PG-RID-001 are
# torque-ON preconditions; PG-STOP-001 is the stop-latency evidence this WP produces. The
# provisional-f_max lineage (PG-RT-001a/b) is WP-1-04's, so its re-derivation trigger is
# imported from that producer at its point of use (see stop_latency), not restated here.
PG_SAFE_001 = "PG-SAFE-001"
PG_RID_001 = "PG-RID-001"
PG_STOP_001 = "PG-STOP-001"

# Registry gate-state machine names (`06` §5, registry/checks/wp.py). A precondition is
# satisfied only at PASS; FAIL_BLOCKING is the state that blocks every torque-ON
# descendant (`02a` §8, PG-SAFE-001 negative branch).
GATE_STATE_PASS = "PASS"
GATE_STATE_FAIL_BLOCKING = "FAIL_BLOCKING"

# The kernel-clock methods that can correlate a deadman release to the CAN stop frame
# (`03` §5.7.0): the evdev kernel timestamp crossed with SO_TIMESTAMPING (A), or an
# independent GPIO marker (B). A `candump` hardware timestamp cannot be correlated to
# the release event and is a forge, so it is not in this set (`03` §5.7.0 forgery ruling).
CLOCK_METHOD_KERNEL_EVDEV_SO_TIMESTAMPING = "kernel_evdev_so_timestamping"
CLOCK_METHOD_INDEPENDENT_GPIO_MARKER = "independent_gpio_marker"
ALLOWED_CLOCK_METHODS = frozenset(
    {CLOCK_METHOD_KERNEL_EVDEV_SO_TIMESTAMPING, CLOCK_METHOD_INDEPENDENT_GPIO_MARKER}
)
# The method a candump capture would claim; naming it lets the artifact refuse it by
# name rather than by the absence of an allowed one, so the forge is rejected loudly.
CLOCK_METHOD_CANDUMP_HW_TIMESTAMP = "candump_hw_timestamp"

# The stop-path percentile the evidence reports (`04` NFR-MAN-002 requires the P99 tail,
# because the Python/GIL path has a fat tail a mean would hide).
STOP_LATENCY_PERCENTILE = 99.0

# `04` NFR-MAN-002's `[unconfirmed]` stop-latency target, milliseconds. Recorded in the
# evidence as a reference only — NEVER a pass/fail threshold (acceptance ⑬). The measured
# P99 is canon; the rig confirms whether the target is met, this code does not judge it.
STOP_LATENCY_TARGET_MS = 20.0

# Environment variable a caller sets to point the re-verification hook at a directory of
# real captures (`02a` §4.1). Until it is set, every hardware acceptance skips with a
# reason rather than being asserted green.
FIXTURE_ENV_VAR = "OPENARM_TORQUE_BRINGUP_REAL_FIXTURE"
