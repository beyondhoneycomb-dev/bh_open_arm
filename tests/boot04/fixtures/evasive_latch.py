"""Violation fixture: a local latch reached through `getattr` rather than by name.

A checker that only understands `scheduler.latch_to_hold(...)` would report this file clean,
which would make the locality rule trivially avoidable by anyone who wanted to avoid it.
"""

from __future__ import annotations

from ops.cancel.scheduler import ActuationScheduler, LatchReason

LATCH_METHOD = "latch_to_hold"


def latch_via_getattr(scheduler: ActuationScheduler, reason: LatchReason) -> None:
    """Apply a hold latch without naming the method at the call site.

    Args:
        scheduler: Scheduler to latch through.
        reason: Cause recorded with the latch.
    """
    getattr(scheduler, "latch_to_hold")(reason)  # noqa: B009
