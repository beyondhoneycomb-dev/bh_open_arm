"""The pending integration: the gateway's accepted output must reach the single writer.

WP-1-03 built the safety gateway (the 8-check filter on `send_action`), the
`ActuationScheduler` single writer, and the mailbox as verified components. What is NOT
built here is the runtime assembly that joins them: `send_action`'s accepted output is
not published onto the scheduler mailbox, so today the full filter is enforced only on
the Robot ABC path while the scheduler emits the position-clamped mailbox target.

This is inert in Wave 1 (offline, no torque-ON, nothing moves). It becomes load-bearing
at WP-1-05, when torque-ON activates: a producer publishing an unsafe-rate target must be
stopped by the 8-check filter, not merely position-clamped. This test names that invariant
and skips until the assembly exists — the re-verification hook for the gap the Wave 1
audit surfaced (P1). Unskip it when WP-1-05 wires the accepted output onto the mailbox.
"""

from __future__ import annotations

import pytest

_ASSEMBLY_PENDING = (
    "runtime assembly (send_action accepted output -> scheduler mailbox) is WP-1-05 torque-ON work"
)


@pytest.mark.skip(reason=_ASSEMBLY_PENDING)
def test_send_action_accepted_output_reaches_the_single_writer() -> None:
    # Once assembled: publishing an unsafe-rate target through send_action must reach the
    # scheduler only after the 8-check filter has accepted (or held) it — the single writer
    # never emits a command the filter did not pass. Asserting this needs the running
    # follower<->scheduler wiring that WP-1-05 builds; until then the components are verified
    # in isolation (tests/wp103/test_send_action_gateway.py, test_scheduler_hold.py).
    raise AssertionError("unreachable: skipped until WP-1-05 builds the runtime assembly")
