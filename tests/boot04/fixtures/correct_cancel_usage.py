"""Pass fixture: cancellation driven from outside `ops/cancel/` the way it is meant to be.

This module cancels a rig stage and therefore causes a latch — but it never applies one itself.
It routes through `cancel_stage`, which is the whole point of the locality rule: code outside
the owning package may *trigger* a latch, it may not *implement* one. The static check must
report zero hits here, or it is over-blocking.
"""

from __future__ import annotations

from ops.cancel.executor import CancelTrace, WorkflowHandle, cancel_stage
from ops.cancel.policy import CancelPolicy
from ops.cancel.scheduler import ActuationScheduler, LatchReason


def cancel_a_rig_stage(
    handle: WorkflowHandle,
    scheduler: ActuationScheduler,
    reason: LatchReason,
    now: float,
    trace: CancelTrace,
) -> None:
    """Cancel a latch-to-hold stage through the owning package.

    Args:
        handle: Instance being cancelled.
        scheduler: Scheduler the executor will latch through.
        reason: Cause recorded with the latch.
        now: Clock reading for trace events.
        trace: Trace to append to.
    """
    cancel_stage(
        handle=handle,
        policy=CancelPolicy.LATCH_TO_HOLD,
        scheduler=scheduler,
        reason=reason,
        now=now,
        trace=trace,
    )
