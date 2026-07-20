"""Acceptance ⑩ — a SHAPE-IM(n) manifest spawns exactly n, and cancelling reclaims all of them.

Also covers the manifest reader's rejections, since a manifest that resolves to the wrong width
or the wrong cancel branch is the input that makes every downstream guarantee wrong.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ops.cancel.executor import BRANCH_CANCELLED, LATCH_TO_HOLD, CancelTrace, verify_cancel_order
from ops.cancel.policy import CancelPolicy, ExecClass, PolicyMismatchError
from ops.cancel.scheduler import LatchReason
from ops.launch.clock import ManualClock
from ops.launch.manifest import ManifestError, Shape, load_manifest, parse_manifest
from ops.launch.spawner import SpawnAdapter
from tests.boot04.doubles import RecordingScheduler

FANOUT_WIDTH = 3


def _im_manifest(width: int, declared: str | None = None) -> dict[str, object]:
    """Build a single-stage SHAPE-IM manifest with the given number of exclusive units.

    Args:
        width: Number of exclusive ownership units.
        declared: Workflow token to write, overriding the default.

    Returns:
        (dict[str, object]): The manifest mapping.
    """
    return {
        "wp_id": "WP-3B-01",
        "workflow": declared or "SHAPE-IM",
        "exec_class": "AI-offline",
        "owns": [{"glob": f"pkg{index}/**", "mode": "EXCLUSIVE"} for index in range(width)],
    }


def test_shape_im_spawns_exactly_n(clock: ManualClock) -> None:
    """Acceptance ⑩ — width comes from the exclusive ownership units."""
    manifest = parse_manifest(_im_manifest(FANOUT_WIDTH))
    adapter = SpawnAdapter(clock)

    result = adapter.spawn(manifest, stage_index=0)

    assert manifest.stage(0).fanout() == FANOUT_WIDTH
    assert len(result.instances) == FANOUT_WIDTH
    assert len(adapter.running()) == FANOUT_WIDTH
    assert len({item.instance_id for item in result.instances}) == FANOUT_WIDTH


def test_declared_width_matching_ownership_is_accepted(clock: ManualClock) -> None:
    """`SHAPE-IM(3)` is accepted when three exclusive units back it."""
    manifest = parse_manifest(_im_manifest(FANOUT_WIDTH, declared="SHAPE-IM(3)"))
    assert manifest.stage(0).fanout() == FANOUT_WIDTH


def test_violation_fixture_declared_width_contradicting_ownership_is_rejected() -> None:
    """A width nobody owns the files for is two truths about the same fan-out."""
    with pytest.raises(ManifestError, match="declared width 5 but owns 3"):
        parse_manifest(_im_manifest(FANOUT_WIDTH, declared="SHAPE-IM(5)"))


def test_cancelling_reclaims_every_instance(
    clock: ManualClock, scheduler: RecordingScheduler, latch_reason: LatchReason
) -> None:
    """Acceptance ⑩ — zero leaks after cancellation."""
    manifest = parse_manifest(_im_manifest(FANOUT_WIDTH))
    adapter = SpawnAdapter(clock)
    adapter.spawn(manifest, stage_index=0)

    reclaimed = adapter.cancel_all(
        stage=manifest.stage(0), scheduler=scheduler, reason=latch_reason, trace=CancelTrace()
    )

    assert reclaimed == FANOUT_WIDTH
    assert adapter.running() == []


def test_reclaim_covers_instances_from_several_spawns(
    clock: ManualClock, scheduler: RecordingScheduler, latch_reason: LatchReason
) -> None:
    """A second fan-out must not leave the first one stranded."""
    manifest = parse_manifest(_im_manifest(FANOUT_WIDTH))
    adapter = SpawnAdapter(clock)
    adapter.spawn(manifest, stage_index=0)
    adapter.spawn(manifest, stage_index=0)

    reclaimed = adapter.cancel_all(
        stage=manifest.stage(0), scheduler=scheduler, reason=latch_reason, trace=CancelTrace()
    )

    assert reclaimed == FANOUT_WIDTH * 2
    assert adapter.running() == []


def test_every_instance_gets_its_own_ordered_cancellation(
    clock: ManualClock, scheduler: RecordingScheduler, latch_reason: LatchReason
) -> None:
    """On a rig stage each instance is latched before it is cancelled, not just the first."""
    manifest = parse_manifest(
        {
            "wp_id": "WP-0B-06",
            "phases": [
                {
                    "workflow": "SHAPE-IM",
                    "exec_class": "AI-on-HW",
                    "cancel_policy": "latch-to-hold",
                    "owns": [
                        {"glob": f"rig{index}/**", "mode": "EXCLUSIVE"}
                        for index in range(FANOUT_WIDTH)
                    ],
                }
            ],
        }
    )
    adapter = SpawnAdapter(clock)
    result = adapter.spawn(manifest, stage_index=0)
    trace = CancelTrace()

    adapter.cancel_all(
        stage=manifest.stage(0), scheduler=scheduler, reason=latch_reason, trace=trace
    )

    assert len(scheduler.reasons) == FANOUT_WIDTH
    for instance in result.instances:
        assert trace.actions_for(instance.instance_id) == [LATCH_TO_HOLD, BRANCH_CANCELLED]
        verify_cancel_order(CancelPolicy.LATCH_TO_HOLD, trace.actions_for(instance.instance_id))


@pytest.mark.parametrize("shape", ["SHAPE-CF", "SHAPE-IG", "SHAPE-HG"])
def test_non_implementation_shapes_run_at_width_one(shape: str) -> None:
    """`01` §1.2 — only SHAPE-IM has a width to choose."""
    exec_class = "Human-judgment" if shape == "SHAPE-HG" else "AI-offline"
    manifest = parse_manifest(
        {"wp_id": "WP-BOOT-04", "workflow": shape, "exec_class": exec_class, "owns": []}
    )
    assert manifest.stage(0).fanout() == 1


def test_measurement_shape_runs_at_width_one() -> None:
    """The rig is one; SHAPE-MS width is physics, not policy."""
    manifest = parse_manifest(
        {"wp_id": "WP-0B-06", "workflow": "SHAPE-MS", "exec_class": "AI-on-HW", "owns": []}
    )
    assert manifest.stage(0).workflow is Shape.MS
    assert manifest.stage(0).fanout() == 1


def test_violation_fixture_widening_a_measurement_stage_is_rejected() -> None:
    """Spawning three measurement instances would deny that there is one rig."""
    with pytest.raises(ManifestError, match="runs at width 1"):
        parse_manifest(
            {
                "wp_id": "WP-0B-06",
                "workflow": "SHAPE-MS(3)",
                "exec_class": "AI-on-HW",
                "owns": [],
            }
        )


def test_violation_fixture_measurement_stage_owning_paths_is_rejected() -> None:
    """`00` §3.2a — a measurement stage reads and measures; it writes nothing."""
    with pytest.raises(ManifestError, match="must own nothing"):
        parse_manifest(
            {
                "wp_id": "WP-0B-06",
                "workflow": "SHAPE-MS",
                "exec_class": "AI-on-HW",
                "owns": [{"glob": "out/**", "mode": "EXCLUSIVE"}],
            }
        )


def test_violation_fixture_implementation_stage_owning_nothing_is_rejected() -> None:
    """A fan-out over zero exclusive write units has nothing to fan out over."""
    with pytest.raises(ManifestError, match="nothing to fan out over"):
        parse_manifest(_im_manifest(0))


@pytest.mark.parametrize("token", ["SHAPE-IM + SHAPE-MS", "SHAPE-IM -> SHAPE-MS", "SHAPE-XX"])
def test_violation_fixture_shape_outside_the_vocabulary_is_rejected(token: str) -> None:
    """`00` §3.2a — one token per field; two tokens are said with phases[]."""
    with pytest.raises(ManifestError):
        parse_manifest(
            {"wp_id": "WP-3B-01", "workflow": token, "exec_class": "AI-offline", "owns": []}
        )


def test_violation_fixture_scalar_and_phases_together_are_rejected() -> None:
    """They are mutually exclusive so that one place answers what is running."""
    with pytest.raises(ManifestError, match="mutually exclusive|exclusive"):
        parse_manifest(
            {
                "wp_id": "WP-3B-01",
                "workflow": "SHAPE-IM",
                "exec_class": "AI-offline",
                "phases": [
                    {
                        "workflow": "SHAPE-IM",
                        "exec_class": "AI-offline",
                        "cancel_policy": "finish-step",
                        "owns": [],
                    }
                ],
            }
        )


def test_violation_fixture_rig_stage_declaring_finish_step_is_rejected() -> None:
    """The safety defect the whole package exists to prevent."""
    with pytest.raises(PolicyMismatchError) as error:
        parse_manifest(
            {
                "wp_id": "WP-0B-06",
                "phases": [
                    {
                        "workflow": "SHAPE-MS",
                        "exec_class": "AI-on-HW",
                        "cancel_policy": "finish-step",
                        "owns": [],
                    }
                ],
            }
        )
    assert error.value.exec_class is ExecClass.AI_ON_HW
    assert error.value.required is CancelPolicy.LATCH_TO_HOLD


def test_violation_fixture_offline_stage_declaring_latch_is_rejected() -> None:
    """Over-application in the manifest, caught before it can reach the executor."""
    with pytest.raises(PolicyMismatchError):
        parse_manifest(
            {
                "wp_id": "WP-BOOT-04",
                "phases": [
                    {
                        "workflow": "SHAPE-CF",
                        "exec_class": "AI-offline",
                        "cancel_policy": "latch-to-hold",
                        "owns": [],
                    }
                ],
            }
        )


def test_violation_fixture_phase_without_cancel_policy_is_rejected() -> None:
    """A stage with no declared policy has no defined cancel branch."""
    with pytest.raises(ManifestError, match="cancel_policy"):
        parse_manifest(
            {
                "wp_id": "WP-3B-01",
                "phases": [{"workflow": "SHAPE-CF", "exec_class": "AI-offline", "owns": []}],
            }
        )


def test_manifest_loads_from_a_file(tmp_path: Path) -> None:
    """The adapter reads manifests off disk, not only from memory."""
    path = tmp_path / "WP-3B-01.yaml"
    path.write_text(yaml.safe_dump(_im_manifest(FANOUT_WIDTH)), encoding="utf-8")

    manifest = load_manifest(path)
    assert manifest.wp_id == "WP-3B-01"
    assert manifest.stage(0).fanout() == FANOUT_WIDTH
