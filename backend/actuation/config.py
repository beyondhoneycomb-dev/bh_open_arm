"""Named parameters of the actuation spine (`WP-0A-01`).

Every literal the tick logic depends on is named here rather than buried at a call
site, so the one place a threshold is decided is the one place it is read.

A deliberate non-decision: **no frequency target is fixed here.** `WP-0A-01` is
measured for correctness, not for a hertz figure — that figure is `PG-RT-001a`,
which comes later (SPINE §2-6). `TICK_INTERVAL_SEC` is therefore a *harness* knob
that drives the controlled clock in fault injection; it is not a claim about the
production loop rate. `RID9_NO_SEND_MARGIN_SEC` is likewise a fail-safe ceiling the
trace must stay under (acceptance ⑧), derived from the RID-9 timeout *semantics*
(`16` M-4: RID 9 is a u32 in 50 µs units), not from a fixed loop rate.
"""

from __future__ import annotations

from contracts.units import Nm, RadPerSec

# Controlled-clock tick spacing used by the fault-injection harness. NOT a
# production loop-rate target (that is PG-RT-001a, deliberately unfixed here).
TICK_INTERVAL_SEC = 0.001

# A mailbox target older than this — measured against the same controlled clock —
# is stale, and the tick that observes it emits STALE_SOURCE_HOLD (acceptance ③).
FRESHNESS_WINDOW_SEC = 0.05

# Deadman renewal lease (U-4, `04` FR-MAN-050). A lease not renewed within this
# window is expired, and the expiry tick emits a hold independent of any producer
# state (acceptance ④).
LEASE_DURATION_SEC = 0.1

# Fail-safe ceiling on the interval between two consecutive CAN sends (acceptance
# ⑧). The "always exactly one emission per tick" invariant makes every tick a
# send, so the observed max interval is bounded by the tick spacing; this margin
# is the number the trace-derived maximum must stay strictly below. It encodes the
# RID-9 hold-refresh deadline (`12` NFR-SAF-007: Cat-2 hold send period < RID-9
# TIMEOUT), sized well above TICK_INTERVAL_SEC.
RID9_NO_SEND_MARGIN_SEC = 0.02

# MIT position-hold gains (`12` §2.7). Stiffness (kp) and damping (kd) are scalar
# MIT gains, dimensionless at this boundary and deliberately not CTR-UNIT physical
# quantities (they cross no unit boundary) — matching `ExecutedMitCommand`.
MIT_HOLD_KP = 40.0
MIT_HOLD_KD = 1.0

# A position-hold and a position command both carry zero feed-forward velocity and
# zero feed-forward torque: the command is position-only (`10` FR-TRN-066), and
# gravity/safety torque is a separate audit channel never mixed in here.
HOLD_VELOCITY = RadPerSec(0.0)
HOLD_TORQUE = Nm(0.0)
