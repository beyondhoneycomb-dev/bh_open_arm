"""Acceptance ③ and ④ — the cancel branch and its ordering, asserted from a call trace.

Two independent observations back every ordering claim: the executor's own `CancelTrace`, and
the shared `call_log` that the scheduler double and the fake workflow write to when they are
actually called. The second is what makes the first trustworthy.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from ops.cancel.executor import (
    BRANCH_CANCELLED,
    LATCH_TO_HOLD,
    STEP_COMPLETED,
    CancelContractError,
    CancelTrace,
    cancel_stage,
    verify_cancel_order,
)
from ops.cancel.policy import CancelPolicy, ExecClass, derive_cancel_policy
from ops.cancel.scheduler import LatchReason
from ops.launch.clock import ManualClock
from ops.launch.spawner import FakeWorkflow, InstanceState
from tests.boot04.doubles import RecordingScheduler

FIXTURE_MODULE = Path(__file__).parent / "fixtures" / "wrong_order_cancel.py"


def _load_wrong_order_fixtures() -> ModuleType:
    """Load the wrong-order fixture module from its path.

    Loading by path keeps the fixture directory off the import path, so nothing can reach these
    implementations by accident.

    Returns:
        (ModuleType): The loaded fixture module.
    """
    spec = importlib.util.spec_from_file_location("wrong_order_cancel", FIXTURE_MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def workflow(call_log: list[str]) -> FakeWorkflow:
    """Provide a fake workflow bound to the shared ordering log.

    Args:
        call_log: Shared ordering log.

    Returns:
        (FakeWorkflow): The instance under cancellation.
    """
    return FakeWorkflow(wp_id="WP-0B-06", stage_index=0, ordinal=0, call_log=call_log)


def test_latch_to_hold_latches_before_cancelling(
    workflow: FakeWorkflow,
    scheduler: RecordingScheduler,
    call_log: list[str],
    latch_reason: LatchReason,
    clock: ManualClock,
) -> None:
    """Acceptance ③ — latch first, cancel second, step never allowed to finish."""
    trace = CancelTrace()
    cancel_stage(
        handle=workflow,
        policy=CancelPolicy.LATCH_TO_HOLD,
        scheduler=scheduler,
        reason=latch_reason,
        now=clock(),
        trace=trace,
    )

    assert call_log == [LATCH_TO_HOLD, BRANCH_CANCELLED]
    assert trace.actions() == [LATCH_TO_HOLD, BRANCH_CANCELLED]
    assert STEP_COMPLETED not in call_log
    assert workflow.state is InstanceState.CANCELLED
    verify_cancel_order(CancelPolicy.LATCH_TO_HOLD, call_log)


def test_latch_carries_the_gate_evidence(
    workflow: FakeWorkflow,
    scheduler: RecordingScheduler,
    latch_reason: LatchReason,
    clock: ManualClock,
) -> None:
    """`05` §5.2 P-0 requires latch time plus {gateId, previous state, new state}."""
    cancel_stage(
        handle=workflow,
        policy=CancelPolicy.LATCH_TO_HOLD,
        scheduler=scheduler,
        reason=latch_reason,
        now=clock(),
        trace=CancelTrace(),
    )

    assert len(scheduler.reasons) == 1
    recorded = scheduler.reasons[0]
    assert recorded.gate_id == "PG-SAFE-001"
    assert recorded.previous_state == "PASS"
    assert recorded.new_state == "FAIL_BLOCKING"
    assert recorded.latched_at == clock()


def test_finish_step_completes_the_step_then_cancels(
    workflow: FakeWorkflow,
    scheduler: RecordingScheduler,
    call_log: list[str],
    latch_reason: LatchReason,
    clock: ManualClock,
) -> None:
    """Acceptance ④ — the step runs to completion and the scheduler is never touched."""
    trace = CancelTrace()
    cancel_stage(
        handle=workflow,
        policy=CancelPolicy.FINISH_STEP,
        scheduler=scheduler,
        reason=latch_reason,
        now=clock(),
        trace=trace,
    )

    assert call_log == [STEP_COMPLETED, BRANCH_CANCELLED]
    assert trace.actions() == [STEP_COMPLETED, BRANCH_CANCELLED]
    assert scheduler.reasons == []
    verify_cancel_order(CancelPolicy.FINISH_STEP, call_log)


def test_violation_fixture_reversed_order_is_rejected(
    workflow: FakeWorkflow,
    scheduler: RecordingScheduler,
    call_log: list[str],
    latch_reason: LatchReason,
    clock: ManualClock,
) -> None:
    """Acceptance ③ — cancelling before latching must be rejected."""
    fixtures = _load_wrong_order_fixtures()
    fixtures.cancel_then_latch(workflow, scheduler, latch_reason, clock(), CancelTrace())

    assert call_log == [BRANCH_CANCELLED, LATCH_TO_HOLD]
    with pytest.raises(CancelContractError, match="after the branch was cancelled"):
        verify_cancel_order(CancelPolicy.LATCH_TO_HOLD, call_log)


def test_violation_fixture_finishing_a_rig_step_is_rejected(
    workflow: FakeWorkflow,
    scheduler: RecordingScheduler,
    call_log: list[str],
    latch_reason: LatchReason,
    clock: ManualClock,
) -> None:
    """Graceful cancellation applied to motion: the latch happens, but too late."""
    fixtures = _load_wrong_order_fixtures()
    fixtures.finish_step_then_latch(workflow, scheduler, latch_reason, clock(), CancelTrace())

    assert call_log == [STEP_COMPLETED, LATCH_TO_HOLD, BRANCH_CANCELLED]
    with pytest.raises(CancelContractError, match="allowed to finish"):
        verify_cancel_order(CancelPolicy.LATCH_TO_HOLD, call_log)


def test_violation_fixture_latching_an_offline_stage_is_rejected(
    workflow: FakeWorkflow,
    scheduler: RecordingScheduler,
    call_log: list[str],
    latch_reason: LatchReason,
    clock: ManualClock,
) -> None:
    """Acceptance ④ — over-application is a defect: an offline stage must not latch."""
    fixtures = _load_wrong_order_fixtures()
    fixtures.latch_an_offline_stage(workflow, scheduler, latch_reason, clock(), CancelTrace())

    assert call_log == [LATCH_TO_HOLD, BRANCH_CANCELLED]
    with pytest.raises(CancelContractError, match="no actuation"):
        verify_cancel_order(CancelPolicy.FINISH_STEP, call_log)


def test_violation_fixture_never_cancelling_is_rejected() -> None:
    """A latch on its own is not a cancellation."""
    with pytest.raises(CancelContractError, match="never cancelled"):
        verify_cancel_order(CancelPolicy.LATCH_TO_HOLD, [LATCH_TO_HOLD])


def test_violation_fixture_missing_latch_is_rejected() -> None:
    """A rig stage that cancels without latching at all."""
    with pytest.raises(CancelContractError, match="no latch"):
        verify_cancel_order(CancelPolicy.LATCH_TO_HOLD, [BRANCH_CANCELLED])


def test_violation_fixture_offline_stage_skipping_its_step_is_rejected() -> None:
    """Tearing an offline artifact in half is the failure finish-step exists to prevent."""
    with pytest.raises(CancelContractError, match="without finishing"):
        verify_cancel_order(CancelPolicy.FINISH_STEP, [BRANCH_CANCELLED])


@pytest.mark.parametrize(
    ("exec_class", "expected"),
    [
        (ExecClass.AI_OFFLINE, CancelPolicy.FINISH_STEP),
        (ExecClass.AI_ON_HW, CancelPolicy.LATCH_TO_HOLD),
        (ExecClass.HUMAN_ASSISTED_HW, CancelPolicy.LATCH_TO_HOLD),
        (ExecClass.HUMAN_JUDGMENT, CancelPolicy.FINISH_STEP),
    ],
)
def test_policy_derivation_matches_the_execution_class_table(
    exec_class: ExecClass, expected: CancelPolicy
) -> None:
    """The four-row table of `05` §5.2.1, reproduced as a test."""
    assert derive_cancel_policy(exec_class) is expected
