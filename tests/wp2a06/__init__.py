"""WP-2A-06 acceptance suite — the stop-path latency regression bench (PG-STOP-001).

Everything here runs on this host: the `disable_torque` precondition over the real stop
path (and a violation fixture proving the reused scan still bites), the four-stage
decomposition over synthetic boundary timestamps, and the reused `clockProvenance` refusal.
The one thing that cannot run here — the real on-rig stop-latency measurement — is skipped
with a reason and wired to the re-verification hook, never asserted green.
"""

from __future__ import annotations
