"""Deliberately wrong cancellation implementations.

Every function here breaks the ordering contract on purpose. They exist so that
`verify_cancel_order` can be shown to fail on something — a checker that has never rejected
anything is not known to be checking anything.

This directory is the one place in the repository where a latch is applied from outside
`ops/cancel/`, and the static-check test excludes it explicitly by path rather than by a name
convention hidden inside the checker. Nothing here is importable by production code.
"""

from __future__ import annotations

from ops.cancel.executor import (
    BRANCH_CANCELLED,
    LATCH_TO_HOLD,
    STEP_COMPLETED,
    CancelTrace,
    WorkflowHandle,
)
from ops.cancel.scheduler import ActuationScheduler, LatchReason


def cancel_then_latch(
    handle: WorkflowHandle,
    scheduler: ActuationScheduler,
    reason: LatchReason,
    now: float,
    trace: CancelTrace,
) -> None:
    """Cancel the branch first and latch afterwards.

    The reversal `02a` §-2.3 WP-BOOT-04 acceptance ③ requires be rejected. On a rig stage the
    window between the two calls is time the arm spends moving on an invalidated basis.

    Args:
        handle: Instance being cancelled.
        scheduler: Scheduler to latch through.
        reason: Cause recorded with the latch.
        now: Clock reading for trace events.
        trace: Trace to append to.
    """
    handle.cancel_branch()
    trace.record(BRANCH_CANCELLED, handle.instance_id, now)
    scheduler.latch_to_hold(reason)
    trace.record(LATCH_TO_HOLD, handle.instance_id, now)


def finish_step_then_latch(
    handle: WorkflowHandle,
    scheduler: ActuationScheduler,
    reason: LatchReason,
    now: float,
    trace: CancelTrace,
) -> None:
    """Let the step finish on a rig stage, then latch and cancel.

    This is graceful cancellation applied to motion: the latch does eventually happen, but the
    arm was allowed to keep moving until the step ended.

    Args:
        handle: Instance being cancelled.
        scheduler: Scheduler to latch through.
        reason: Cause recorded with the latch.
        now: Clock reading for trace events.
        trace: Trace to append to.
    """
    handle.complete_current_step()
    trace.record(STEP_COMPLETED, handle.instance_id, now)
    scheduler.latch_to_hold(reason)
    trace.record(LATCH_TO_HOLD, handle.instance_id, now)
    handle.cancel_branch()
    trace.record(BRANCH_CANCELLED, handle.instance_id, now)


def latch_an_offline_stage(
    handle: WorkflowHandle,
    scheduler: ActuationScheduler,
    reason: LatchReason,
    now: float,
    trace: CancelTrace,
) -> None:
    """Latch a stage that has no actuation, instead of letting its step finish.

    Over-application, which acceptance ④ classes as a defect in its own right: the step is torn
    in half and a hold latch is emitted for a stage that never touched the arm.

    Args:
        handle: Instance being cancelled.
        scheduler: Scheduler to latch through.
        reason: Cause recorded with the latch.
        now: Clock reading for trace events.
        trace: Trace to append to.
    """
    scheduler.latch_to_hold(reason)
    trace.record(LATCH_TO_HOLD, handle.instance_id, now)
    handle.cancel_branch()
    trace.record(BRANCH_CANCELLED, handle.instance_id, now)
