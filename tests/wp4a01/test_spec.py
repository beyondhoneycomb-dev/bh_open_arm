"""The job contract is FR-TRN-027 verbatim and the state set is the six values.

These guard against field invention (the batch's explicit ban) and against the
state set drifting from `02c` §1.1.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.training.orchestrator import (
    DatasetRef,
    JobFilter,
    JobSpec,
    JobSpecError,
    JobState,
    apply_filter,
    can_transition,
)
from tests.wp4a01._support import make_spec

# FR-TRN-027 verbatim: {job_id, name, config_snapshot, dataset.repo_id+revision,
# requested_gpus, state, created/started/ended, output_dir}. Nothing more.
_FR_TRN_027_FIELDS = {
    "job_id",
    "name",
    "config_snapshot",
    "dataset",
    "requested_gpus",
    "state",
    "created",
    "started",
    "ended",
    "output_dir",
}


def test_jobspec_fields_are_fr_trn_027_verbatim() -> None:
    assert {field.name for field in dataclasses.fields(JobSpec)} == _FR_TRN_027_FIELDS


def test_dataset_ref_is_repo_id_and_revision() -> None:
    assert {field.name for field in dataclasses.fields(DatasetRef)} == {"repo_id", "revision"}


def test_jobstate_is_exactly_six_values() -> None:
    assert {state.value for state in JobState} == {
        "QUEUED",
        "PREFLIGHT",
        "RUNNING",
        "CANCELLED",
        "FAILED",
        "DONE",
    }


def test_config_snapshot_is_immutable(tmp_path: object) -> None:
    mutable = {"steps": 10, "resume": False}
    spec = JobSpec(
        job_id="j1",
        name="j1",
        config_snapshot=mutable,
        dataset=DatasetRef(repo_id="r", revision="v1"),
        requested_gpus=1,
        state=JobState.QUEUED,
        created=0.0,
        started=None,
        ended=None,
        output_dir="/tmp/out",
    )
    # Mutating the source dict after construction must not leak in.
    mutable["steps"] = 999
    assert spec.config_snapshot["steps"] == 10
    # The snapshot itself rejects writes.
    with pytest.raises(TypeError):
        spec.config_snapshot["steps"] = 1  # type: ignore[index]


def test_missing_required_fields_rejected() -> None:
    with pytest.raises(JobSpecError):
        JobSpec(
            job_id="",
            name="n",
            config_snapshot={},
            dataset=DatasetRef(repo_id="r", revision="v"),
            requested_gpus=1,
            state=JobState.QUEUED,
            created=0.0,
            started=None,
            ended=None,
            output_dir="/tmp/out",
        )


def test_requested_gpus_must_be_positive() -> None:
    with pytest.raises(JobSpecError):
        JobSpec(
            job_id="j",
            name="n",
            config_snapshot={},
            dataset=DatasetRef(repo_id="r", revision="v"),
            requested_gpus=0,
            state=JobState.QUEUED,
            created=0.0,
            started=None,
            ended=None,
            output_dir="/tmp/out",
        )


def test_legal_transitions_follow_the_table() -> None:
    assert can_transition(JobState.QUEUED, JobState.PREFLIGHT)
    assert can_transition(JobState.PREFLIGHT, JobState.RUNNING)
    assert can_transition(JobState.RUNNING, JobState.DONE)
    assert can_transition(JobState.RUNNING, JobState.CANCELLED)
    assert can_transition(JobState.CANCELLED, JobState.QUEUED)
    assert can_transition(JobState.FAILED, JobState.QUEUED)


def test_illegal_transitions_rejected() -> None:
    assert not can_transition(JobState.DONE, JobState.QUEUED)
    assert not can_transition(JobState.QUEUED, JobState.RUNNING)
    assert not can_transition(JobState.PREFLIGHT, JobState.DONE)


def test_filter_and_sort(tmp_path: object) -> None:
    from pathlib import Path

    base = Path(str(tmp_path))
    specs = [
        make_spec("b", base / "b"),
        make_spec("a", base / "a"),
        make_spec("c", base / "c"),
    ]
    specs[1].state = JobState.RUNNING
    by_name = apply_filter(specs, JobFilter(sort_by="name"))
    assert [spec.job_id for spec in by_name] == ["a", "b", "c"]
    running = apply_filter(specs, JobFilter(states=frozenset({JobState.RUNNING})))
    assert [spec.job_id for spec in running] == ["a"]
