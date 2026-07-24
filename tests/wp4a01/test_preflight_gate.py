"""OBS-1 — the orchestrator's PREFLIGHT state actually preflights and gates RUNNING.

Before this wiring the PREFLIGHT state was a pass-through: a job could reach RUNNING
and spawn `lerobot-train` without preflight ever running or a `TrainingClearance`
being obtained. These tests prove the gap is closed for the three runtime cases
(`02c` §1.2/§1.3, `FR-TRN-068`):

  ① a BLOCK-ing dataset never reaches RUNNING, carries its findings, spawns nothing;
  ② a job with an undecided degenerate finding parks awaiting the three-way choice and
     only proceeds once decided;
  ③ a clean job reaches RUNNING through a genuinely-minted clearance and records its
     WP-4A-05 lineage on launch.

Each faulted case supplies its own `PreflightProvider`, describing a real dataset the
committed WP-4A-02/03 fixtures define — the checker is exercised, never bypassed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.training.degenerate import (
    DegenerateChoice,
    DegenerateDecision,
    DegenerateFinding,
    NormMode,
)
from backend.training.lineage import CheckpointId, LineageRecorder, TrainingLineageStore
from backend.training.orchestrator import (
    JobState,
    LaunchLineage,
    OrchestratorError,
    PreflightContext,
)
from backend.training.orchestrator.checkpoints import find_last
from backend.training.preflight import Component, PreflightCode, Verdict
from tests.wp4a01._support import make_orchestrator, make_spec
from tests.wp4a02.fixtures import clean_pair, fault_torque_stripped
from tests.wp4a05.support import fixture_record


class _BlockProvider:
    """Describes a torque-stripped dataset that WP-4A-02 preflight must BLOCK."""

    def context_for(self, spec: object) -> PreflightContext:
        case = fault_torque_stripped()
        return PreflightContext(dataset=case.dataset, policy=case.policy)


class _UndecidedProvider:
    """A clean (PASS) dataset carrying one undecided degenerate finding."""

    def __init__(self, finding: DegenerateFinding) -> None:
        self.mFinding = finding

    def context_for(self, spec: object) -> PreflightContext:
        dataset, policy = clean_pair()
        return PreflightContext(
            dataset=dataset, policy=policy, degenerate_findings=(self.mFinding,)
        )


class _FixedLineagePlanner:
    """Returns a valid WP-4A-05 launch lineage, with element (h) from the clearance."""

    def __init__(self, checkpoint: CheckpointId, dataset_content_hash: str) -> None:
        self.mCheckpoint = checkpoint
        self.mHash = dataset_content_hash

    def plan(self, spec: object, clearance: object) -> LaunchLineage:
        record = fixture_record(degenerate_decisions=list(clearance.decisions))  # type: ignore[attr-defined]
        return LaunchLineage(
            record=record, checkpoint=self.mCheckpoint, dataset_content_hash=self.mHash
        )


def _sample_finding() -> DegenerateFinding:
    """One stationary-velocity degenerate finding (`02c` §1.3), located by name."""
    return DegenerateFinding(
        channel_name="left_joint_2.vel",
        joint="left_joint_2",
        component=Component.VEL,
        norm_mode=NormMode.MEAN_STD,
        statistic=0.0,
        threshold=1e-3,
        amplification_estimate=1e8,
    )


def test_blocking_dataset_never_reaches_running(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path, preflight_provider=_BlockProvider())
    out = tmp_path / "run"  # fresh dir: the output-dir check does not pre-empt the gate

    runtime = orchestrator.submit(make_spec("job", out, steps=4, save_freq=1))

    # It did not start: never RUNNING, no subprocess handle, no checkpoint written.
    assert runtime.spec.state is JobState.FAILED
    assert runtime.handle is None
    assert runtime.gate.clearance is None
    assert find_last(out) is None
    assert not orchestrator.mLogStore.exists("job")

    # The BLOCK findings are attached so the rejection is actionable.
    report = runtime.gate.report
    assert report is not None
    assert report.verdict is Verdict.BLOCK
    assert PreflightCode.OBSERVATION_STATE_ORDER in report.codes()


def test_undecided_finding_parks_then_proceeds_once_decided(tmp_path: Path) -> None:
    finding = _sample_finding()
    orchestrator = make_orchestrator(tmp_path, preflight_provider=_UndecidedProvider(finding))
    out = tmp_path / "run"

    runtime = orchestrator.submit(make_spec("job", out, hold_at_step=0))

    # Preflight PASSed, but the finding is undecided: the job parks in PREFLIGHT
    # holding its GPU, never RUNNING, no subprocess, no clearance.
    assert runtime.spec.state is JobState.PREFLIGHT
    assert runtime.gate.awaiting_decisions is True
    assert runtime.handle is None
    assert runtime.gate.clearance is None
    assert find_last(out) is None

    # An empty decision set does not clear it — it stays parked.
    assert orchestrator.decide("job", []) is JobState.PREFLIGHT
    assert runtime.spec.state is JobState.PREFLIGHT
    assert runtime.handle is None

    # Recording the three-way choice clears the job; it launches in the same call.
    decision = DegenerateDecision(
        finding=finding, choice=DegenerateChoice.PROCEED, rationale="accepted knowingly"
    )
    assert orchestrator.decide("job", [decision]) is JobState.RUNNING
    assert runtime.spec.state is JobState.RUNNING
    assert runtime.handle is not None
    assert runtime.gate.clearance is not None

    orchestrator.cancel("job")


def test_decide_on_a_job_not_awaiting_is_rejected(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path)  # clean provider: the job never parks
    orchestrator.submit(make_spec("job", tmp_path / "run", hold_at_step=0))

    # The job is RUNNING (no undecided finding), so there is nothing to decide.
    assert orchestrator.get("job").spec.state is JobState.RUNNING
    with pytest.raises(OrchestratorError):
        orchestrator.decide("job", [])
    orchestrator.cancel("job")


def test_clean_job_reaches_running_and_records_lineage(tmp_path: Path) -> None:
    out = tmp_path / "run"
    store = TrainingLineageStore(tmp_path / "train_lineage")
    checkpoint = CheckpointId(output_dir=str(out), step=0)
    planner = _FixedLineagePlanner(checkpoint=checkpoint, dataset_content_hash="ds-content-0001")
    orchestrator = make_orchestrator(
        tmp_path, lineage_recorder=LineageRecorder(store), lineage_planner=planner
    )

    runtime = orchestrator.submit(make_spec("job", out, hold_at_step=0))

    # A clean dataset clears through a genuinely-minted clearance and runs.
    assert runtime.spec.state is JobState.RUNNING
    assert runtime.gate.clearance is not None

    # Its WP-4A-05 lineage was recorded on launch and is queryable.
    snapshot = store.snapshot_of(checkpoint)
    assert snapshot is not None
    # A clean job has no degenerate decisions: element (h) is present and empty.
    assert snapshot.degenerate_decisions == ()

    orchestrator.cancel("job")
    store.close()
