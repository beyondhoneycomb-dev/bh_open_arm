"""Acceptance ⑪ — both cancel branches demonstrated within ONE multi-stage work package.

This is the criterion that distinguishes branching on the active stage from branching on the
package's maximum class. The package below has a maximum class of `AI-on-HW`; if the branch were
chosen from that, stage 0 would latch, and the test asserting it finishes its step would fail.
"""

from __future__ import annotations

import pytest

from ops.cancel.executor import (
    BRANCH_CANCELLED,
    LATCH_TO_HOLD,
    STEP_COMPLETED,
    CancelTrace,
    verify_cancel_order,
)
from ops.cancel.policy import CancelPolicy, ExecClass
from ops.cancel.scheduler import LatchReason
from ops.launch.clock import ManualClock
from ops.launch.manifest import Manifest, Shape, parse_manifest
from ops.launch.spawner import InstanceState, SpawnAdapter
from tests.boot04.doubles import RecordingScheduler

OFFLINE_STAGE = 0
RIG_STAGE = 1

# One package that computes offline, then measures on the rig: the shape `00` §3.2a exists for.
MULTI_STAGE_MANIFEST: dict[str, object] = {
    "wp_id": "WP-0B-07",
    "phases": [
        {
            "workflow": "SHAPE-IM",
            "exec_class": "AI-offline",
            "cancel_policy": "finish-step",
            "owns": [{"glob": "calib/solver/**", "mode": "EXCLUSIVE"}],
        },
        {
            "workflow": "SHAPE-MS",
            "exec_class": "AI-on-HW",
            "cancel_policy": "latch-to-hold",
            "owns": [],
            "after": 0,
        },
    ],
}


@pytest.fixture
def manifest() -> Manifest:
    """Provide the two-stage manifest.

    Returns:
        (Manifest): Offline stage followed by a rig stage.
    """
    return parse_manifest(MULTI_STAGE_MANIFEST)


def _adapter_on(clock: ManualClock, call_log: list[str]) -> SpawnAdapter:
    """Build a spawn adapter whose instances write into the shared ordering log.

    The adapter hands its own log to every instance it spawns, so it must be pointed at the
    shared list before spawning; otherwise the scheduler and the workflows record into two
    separate lists and their relative order cannot be observed at all.

    Args:
        clock: Controlled clock.
        call_log: Shared ordering log.

    Returns:
        (SpawnAdapter): Adapter wired to that log.
    """
    adapter = SpawnAdapter(clock)
    adapter.call_log = call_log
    return adapter


def test_the_package_really_is_multi_stage(manifest: Manifest) -> None:
    assert manifest.is_multi_stage()
    assert manifest.stage(OFFLINE_STAGE).workflow is Shape.IM
    assert manifest.stage(OFFLINE_STAGE).exec_class is ExecClass.AI_OFFLINE
    assert manifest.stage(OFFLINE_STAGE).cancel_policy is CancelPolicy.FINISH_STEP
    assert manifest.stage(RIG_STAGE).workflow is Shape.MS
    assert manifest.stage(RIG_STAGE).exec_class is ExecClass.AI_ON_HW
    assert manifest.stage(RIG_STAGE).cancel_policy is CancelPolicy.LATCH_TO_HOLD


def test_offline_stage_cancellation_finishes_the_step(
    manifest: Manifest,
    clock: ManualClock,
    scheduler: RecordingScheduler,
    latch_reason: LatchReason,
    call_log: list[str],
) -> None:
    """Stage 0 of a package whose maximum class is AI-on-HW must still finish its step."""
    adapter = _adapter_on(clock, call_log)
    result = adapter.spawn(manifest, stage_index=OFFLINE_STAGE)
    trace = CancelTrace()

    adapter.cancel_all(
        stage=manifest.stage(OFFLINE_STAGE),
        scheduler=scheduler,
        reason=latch_reason,
        trace=trace,
    )

    assert call_log == [STEP_COMPLETED, BRANCH_CANCELLED]
    assert scheduler.reasons == [], "an offline stage must not latch the scheduler"
    assert result.instances[0].state is InstanceState.CANCELLED
    verify_cancel_order(CancelPolicy.FINISH_STEP, call_log)


def test_rig_stage_cancellation_latches_immediately(
    manifest: Manifest,
    clock: ManualClock,
    scheduler: RecordingScheduler,
    latch_reason: LatchReason,
    call_log: list[str],
) -> None:
    """Stage 1 of the same package latches first and never finishes its step."""
    adapter = _adapter_on(clock, call_log)
    adapter.spawn(manifest, stage_index=RIG_STAGE)
    trace = CancelTrace()

    adapter.cancel_all(
        stage=manifest.stage(RIG_STAGE), scheduler=scheduler, reason=latch_reason, trace=trace
    )

    assert call_log == [LATCH_TO_HOLD, BRANCH_CANCELLED]
    assert len(scheduler.reasons) == 1
    assert STEP_COMPLETED not in call_log
    verify_cancel_order(CancelPolicy.LATCH_TO_HOLD, call_log)


def test_both_branches_are_reachable_in_one_package(
    manifest: Manifest, clock: ManualClock, latch_reason: LatchReason
) -> None:
    """Acceptance ⑪ — the two branches side by side, traced from the same manifest."""
    traces: dict[int, list[str]] = {}
    for stage_index in (OFFLINE_STAGE, RIG_STAGE):
        log: list[str] = []
        adapter = _adapter_on(clock, log)
        adapter.spawn(manifest, stage_index=stage_index)
        adapter.cancel_all(
            stage=manifest.stage(stage_index),
            scheduler=RecordingScheduler(log),
            reason=latch_reason,
            trace=CancelTrace(),
        )
        traces[stage_index] = log

    assert traces[OFFLINE_STAGE] == [STEP_COMPLETED, BRANCH_CANCELLED]
    assert traces[RIG_STAGE] == [LATCH_TO_HOLD, BRANCH_CANCELLED]
    assert traces[OFFLINE_STAGE] != traces[RIG_STAGE]


def test_maximum_class_would_give_the_wrong_answer_for_stage_zero(manifest: Manifest) -> None:
    """The package's maximum class is AI-on-HW, yet stage 0 must cancel as finish-step.

    Stated as a test because it is the one distinction the acceptance criterion is about: any
    implementation reading the package rather than the active stage disagrees with this.
    """
    maximum_class = max(
        (stage.exec_class for stage in manifest.stages),
        key=_rig_first,
    )
    assert maximum_class is ExecClass.AI_ON_HW
    assert manifest.stage(OFFLINE_STAGE).cancel_policy is CancelPolicy.FINISH_STEP


def _rig_first(exec_class: ExecClass) -> int:
    """Rank execution classes so the rig-touching ones sort highest.

    Args:
        exec_class: Class to rank.

    Returns:
        (int): 1 for classes that touch the rig, 0 otherwise.
    """
    return 1 if exec_class in {ExecClass.AI_ON_HW, ExecClass.HUMAN_ASSISTED_HW} else 0
