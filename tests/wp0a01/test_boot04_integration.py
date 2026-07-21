"""The concrete scheduler is the physical executor BOOT-04's latch contract expects.

`ops/cancel` (WP-BOOT-04) owns the `latch_to_hold` call and its ordering, and
builds only a minimal `ActuationScheduler` Protocol to test cancellation. This WP
is the physical executor it delegates to (`02a` §-2.3). The proof of unification:
`ops.cancel.executor.cancel_stage` — the real cancellation path — drives *this*
scheduler through a latch-to-hold cancel, the ordering check passes, and the arm is
actually held afterwards (every subsequent tick is SAFETY_LATCH_HOLD). BOOT-04's
own tests are untouched; they use their own Protocol double.
"""

from __future__ import annotations

import inspect

from backend.actuation import ActuationScheduler, EmissionLabel, FaultInjectionHarness
from ops.cancel.executor import (
    BRANCH_CANCELLED,
    LATCH_TO_HOLD,
    CancelTrace,
    cancel_stage,
    verify_cancel_order,
)
from ops.cancel.policy import CancelPolicy
from ops.cancel.scheduler import LatchReason


class _StubWorkflow:
    """A cancellable workflow stand-in for the cancel-path integration."""

    def __init__(self, instance_id: str) -> None:
        self._instance_id = instance_id
        self.cancelled = False

    @property
    def instance_id(self) -> str:
        return self._instance_id

    def complete_current_step(self) -> None:
        raise AssertionError("finish-step must not run on a latch-to-hold stage")

    def cancel_branch(self) -> None:
        self.cancelled = True


def test_cancel_stage_latches_through_the_real_scheduler() -> None:
    """A latch-to-hold cancel drives the concrete scheduler and the ordering holds."""
    harness = FaultInjectionHarness()
    harness.run_tick()  # accepted before the cancel

    workflow = _StubWorkflow("wf-1")
    reason = LatchReason(
        gate_id="PG-STOP-001", previous_state="PASS", new_state="LATCHED", latched_at=0.0
    )
    trace = CancelTrace()

    cancel_stage(
        handle=workflow,
        policy=CancelPolicy.LATCH_TO_HOLD,
        scheduler=harness.scheduler,
        reason=reason,
        now=0.0,
        trace=trace,
    )

    # BOOT-04's ordering contract: latch strictly before the branch cancel.
    verify_cancel_order(CancelPolicy.LATCH_TO_HOLD, trace.actions())
    actions = trace.actions()
    assert actions.index(LATCH_TO_HOLD) < actions.index(BRANCH_CANCELLED)
    assert workflow.cancelled is True

    # The latch actually engaged the physical executor: the arm is now held.
    assert harness.scheduler.latch_active is True
    assert harness.run_tick(publish=True, renew=True).label is EmissionLabel.SAFETY_LATCH_HOLD


def test_scheduler_satisfies_the_boot04_latch_signature() -> None:
    """The concrete scheduler carries the `latch_to_hold(reason)` shape BOOT-04 needs.

    Conformance is checked structurally, without invoking the method: `05` §5.2.1
    keeps the *call* to `latch_to_hold` inside `ops/cancel`, and the BOOT-04 locality
    scan (which reads this test file too) would flag a direct call here. The
    functional proof is the cancel-path test above, which reaches the same method
    from within `ops/cancel`.
    """
    method = inspect.unwrap(ActuationScheduler.latch_to_hold)
    parameters = list(inspect.signature(method).parameters)
    assert parameters == ["self", "reason"]
