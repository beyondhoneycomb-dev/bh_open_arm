"""Stage-scoped cancellation: the branch, the ordering, and the check that proves it.

The rule this module exists to enforce (`02a` §-2.3 WP-BOOT-04 contract column): cancellation
branches on the cancel policy of the CURRENTLY ACTIVE STAGE, never on the package's maximum
class. A multi-stage package therefore cancels differently depending on where it is.

  finish-step     let the current step complete, then cancel the branch. Tearing an artifact in
                  half is the more expensive failure when physical risk is zero.
  latch-to-hold   latch first, cancel second. `05` §5.2.1 is unambiguous that closure
                  computation must not delay the latch: P-0 does not take the closure as input.

Trace fidelity: each event is recorded AFTER the call it describes returns, so trace order is
observed call order rather than intended order. An implementation that latched after cancelling
would produce a trace in that same wrong order, which is what makes `verify_cancel_order`
capable of failing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from ops.cancel.policy import CancelPolicy
from ops.cancel.scheduler import ActuationScheduler, LatchReason

LATCH_TO_HOLD = "latch_to_hold"
STEP_COMPLETED = "step_completed"
BRANCH_CANCELLED = "branch_cancelled"


class CancelContractError(Exception):
    """Raised when an observed cancellation sequence breaks the ordering contract."""


class WorkflowHandle(Protocol):
    """A cancellable workflow instance.

    Implementations in this bootstrap are simulated: `WP-BOOT-04` is an `AI-offline` package and
    spawns fake workflows under a controlled clock.
    """

    @property
    def instance_id(self) -> str:
        """Identity of this instance.

        Returns:
            (str): Stable id used in traces and leak accounting.
        """
        ...

    def complete_current_step(self) -> None:
        """Run the in-flight step to completion. Only ever called on a finish-step stage."""
        ...

    def cancel_branch(self) -> None:
        """Cancel the workflow branch and release its resources."""
        ...


@dataclass(frozen=True)
class TraceEvent:
    """One observed action during cancellation."""

    action: str
    instance_id: str
    at: float


@dataclass
class CancelTrace:
    """Ordered record of what cancellation actually did."""

    events: list[TraceEvent] = field(default_factory=list)

    def record(self, action: str, instance_id: str, at: float) -> None:
        """Append an event that has already happened.

        Args:
            action: One of the module-level action constants.
            instance_id: Instance the action applied to.
            at: Clock reading taken when the action completed.
        """
        self.events.append(TraceEvent(action=action, instance_id=instance_id, at=at))

    def actions(self) -> list[str]:
        """List the actions in observed order.

        Returns:
            (list[str]): Action names, oldest first.
        """
        return [event.action for event in self.events]

    def actions_for(self, instance_id: str) -> list[str]:
        """List one instance's actions in observed order.

        Args:
            instance_id: Instance to filter on.

        Returns:
            (list[str]): Action names for that instance, oldest first.
        """
        return [event.action for event in self.events if event.instance_id == instance_id]


def cancel_stage(
    handle: WorkflowHandle,
    policy: CancelPolicy,
    scheduler: ActuationScheduler,
    reason: LatchReason,
    now: float,
    trace: CancelTrace,
) -> None:
    """Cancel one workflow instance according to its active stage's cancel policy.

    Args:
        handle: The workflow instance being cancelled.
        policy: Cancel policy of the stage that is currently active.
        scheduler: Scheduler to latch through; untouched on a finish-step stage.
        reason: Cause recorded with the latch.
        now: Clock reading for trace events.
        trace: Trace to append observed actions to.
    """
    if policy is CancelPolicy.LATCH_TO_HOLD:
        scheduler.latch_to_hold(reason)
        trace.record(LATCH_TO_HOLD, handle.instance_id, now)
        handle.cancel_branch()
        trace.record(BRANCH_CANCELLED, handle.instance_id, now)
        return

    handle.complete_current_step()
    trace.record(STEP_COMPLETED, handle.instance_id, now)
    handle.cancel_branch()
    trace.record(BRANCH_CANCELLED, handle.instance_id, now)


def verify_cancel_order(policy: CancelPolicy, calls: Sequence[str]) -> None:
    """Judge an observed call sequence against the ordering contract.

    Both directions are failures. Under `latch-to-hold`, latching after the cancel (or running
    the step to completion at all) leaves the arm moving on an invalidated basis. Under
    `finish-step`, latching is over-application, which acceptance ④ classes as a defect in its
    own right.

    Args:
        policy: Cancel policy of the stage that was active.
        calls: Observed actions in order.

    Raises:
        CancelContractError: The sequence breaks the contract for that policy.
    """
    if BRANCH_CANCELLED not in calls:
        raise CancelContractError(f"{policy.value}: branch was never cancelled: {list(calls)}")
    cancel_at = calls.index(BRANCH_CANCELLED)

    if policy is CancelPolicy.LATCH_TO_HOLD:
        if LATCH_TO_HOLD not in calls:
            raise CancelContractError(
                f"latch-to-hold: no latch was issued before cancelling: {list(calls)}"
            )
        if calls.index(LATCH_TO_HOLD) > cancel_at:
            raise CancelContractError(
                f"latch-to-hold: latch issued after the branch was cancelled: {list(calls)}"
            )
        if STEP_COMPLETED in calls:
            raise CancelContractError(
                f"latch-to-hold: current step was allowed to finish: {list(calls)}"
            )
        return

    if LATCH_TO_HOLD in calls:
        raise CancelContractError(
            f"finish-step: latch applied to a stage with no actuation: {list(calls)}"
        )
    if STEP_COMPLETED not in calls:
        raise CancelContractError(
            f"finish-step: branch cancelled without finishing the step: {list(calls)}"
        )
    if calls.index(STEP_COMPLETED) > cancel_at:
        raise CancelContractError(
            f"finish-step: step finished after the branch was cancelled: {list(calls)}"
        )
