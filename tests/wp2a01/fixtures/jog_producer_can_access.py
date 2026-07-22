"""A jog producer reaching for the CAN handle — the acceptance-① violation fixture.

Scanning this must produce a finding: it imports the CAN writer and writes the bus
directly instead of publishing to the mailbox — the single-writer breach the scan
(`backend.actuation.staticcheck.find_producer_can_access`) exists to reject. It
lives here, outside `backend/jog`, so it proves the scan bites without putting a CAN
symbol on the real producer path (which acceptance ① requires to be empty).
"""

from __future__ import annotations

from backend.actuation.can_writer import FakeCanWriter
from contracts.action import ExecutedMitCommand


def sneak_jog_write(batch: tuple[ExecutedMitCommand, ...]) -> None:
    """Bypass the mailbox and write a jog frame straight to a CAN handle (forbidden).

    Args:
        batch: A MIT batch a jog producer has no business sending.
    """
    writer = FakeCanWriter()
    writer.mit_control_batch(batch)
