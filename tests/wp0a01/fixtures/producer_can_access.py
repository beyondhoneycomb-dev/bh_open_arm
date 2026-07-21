"""A producer reaching for the CAN handle — the acceptance-⑥ violation fixture.

Scanning this must produce a finding: it imports the CAN writer and calls the bus
write directly, bypassing the mailbox — exactly the single-writer breach the scan
(`backend.actuation.staticcheck.find_producer_can_access`) exists to reject.
"""

from __future__ import annotations

from backend.actuation.can_writer import FakeCanWriter
from contracts.action import ExecutedMitCommand


def sneak_write(batch: tuple[ExecutedMitCommand, ...]) -> None:
    """Bypass the mailbox and write straight to a CAN handle (forbidden).

    Args:
        batch: A MIT batch the producer has no business sending.
    """
    writer = FakeCanWriter()
    writer.mit_control_batch(batch)
