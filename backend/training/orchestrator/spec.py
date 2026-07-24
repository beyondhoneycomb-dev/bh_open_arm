"""The job record contract: `JobSpec`, `JobState`, and the legal transitions.

These fields are `FR-TRN-027` verbatim (`10` §3.6) and the state set is the
six-value contract `02c` §1.1 fixes: no field is invented and no state is added.

`10` §4.1 writes the transition table with seven state names
(`REJECTED`/`COMPLETED`/`CRASHED` among them). `02c` §1.1 collapses that table
onto six values, and this module is the collapse: `REJECTED` and `CRASHED` both
land on `FAILED`, `COMPLETED` lands on `DONE`. The distinction the collapse would
lose — a preflight rejection vs. a mid-run crash vs. an OOM — is not discarded; it
is carried on the runtime record (exit code, signal, the preflight decision)
rather than on the state name, which is where `FR-OPS-024`'s classification wants
it anyway.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any


class JobState(StrEnum):
    """Lifecycle state of one training job (`02c` §1.1, six values, no more).

    QUEUED     created and waiting; either for a GPU or for pre-validation.
    PREFLIGHT  a GPU is held; dimension/stats/output-dir checks are running.
    RUNNING    the `lerobot-train` subprocess is live.
    CANCELLED  a user cancel stopped it; the last checkpoint is preserved.
    FAILED     rejected at preflight, or the process died abnormally (crash/OOM).
    DONE       reached `step == steps` and saved the final checkpoint.
    """

    QUEUED = "QUEUED"
    PREFLIGHT = "PREFLIGHT"
    RUNNING = "RUNNING"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    DONE = "DONE"


# The legal transitions, `10` §4.1 mapped onto the six-value set. FAILED and
# CANCELLED re-enter QUEUED because `10` §4.1's CRASHED/CANCELLED --resume--> QUEUED
# edge is how FR-TRN-033 resume is expressed; the orchestrator additionally refuses
# a resume with no checkpoint behind it.
_TRANSITIONS: Mapping[JobState, frozenset[JobState]] = MappingProxyType(
    {
        JobState.QUEUED: frozenset({JobState.PREFLIGHT, JobState.FAILED, JobState.CANCELLED}),
        JobState.PREFLIGHT: frozenset({JobState.RUNNING, JobState.FAILED}),
        JobState.RUNNING: frozenset({JobState.DONE, JobState.CANCELLED, JobState.FAILED}),
        JobState.CANCELLED: frozenset({JobState.QUEUED}),
        JobState.FAILED: frozenset({JobState.QUEUED}),
        JobState.DONE: frozenset(),
    }
)

TERMINAL_STATES = frozenset({JobState.DONE})


def can_transition(current: JobState, target: JobState) -> bool:
    """Report whether `current -> target` is a legal state transition.

    Args:
        current: The state the job is in.
        target: The state being proposed.

    Returns:
        (bool) True when the transition appears in the `10` §4.1 table.
    """
    return target in _TRANSITIONS[current]


class JobSpecError(Exception):
    """Raised when a `JobSpec` is missing a field the contract requires."""


@dataclass(frozen=True)
class DatasetRef:
    """The dataset axis of a job: a `repo_id` and its git `revision`.

    Both halves are the version key. `10` §2.8 is explicit that a LeRobot dataset
    is versioned by `repo_id` + git revision, so a job that dropped the revision
    would name a moving target.
    """

    repo_id: str
    revision: str


@dataclass
class JobSpec:
    """One training job, exactly the `FR-TRN-027` field set.

    `config_snapshot` is stored as a read-only view over a deep copy of the input,
    which is the "설정 스냅샷 불변 기록" of `10` §4.1: once a job is created its
    configuration cannot drift, even if the caller keeps mutating the dict it
    passed. `state`, `started`, and `ended` are the mutable lifecycle fields the
    same requirement lists; everything else is fixed at creation.

    Runtime bookkeeping a run accrues — the GPU it landed on, its pid, its exit
    code, the step it stopped at — is deliberately NOT here. That belongs on the
    orchestrator's runtime record so this stays the contract and nothing more.

    Attributes:
        job_id: Stable unique id.
        name: Human-facing label.
        config_snapshot: Immutable LeRobot train configuration for this run.
        dataset: The dataset repo_id + revision.
        requested_gpus: How many GPUs the job asks for (1 unless multi-GPU).
        state: Current lifecycle state.
        created: Wall-clock creation time (seconds).
        started: Wall-clock start time, or None until it runs.
        ended: Wall-clock end time, or None until it finishes.
        output_dir: Run output directory.
    """

    job_id: str
    name: str
    config_snapshot: Mapping[str, Any]
    dataset: DatasetRef
    requested_gpus: int
    state: JobState
    created: float
    started: float | None
    ended: float | None
    output_dir: str

    def __post_init__(self) -> None:
        """Validate the field set and freeze the configuration snapshot."""
        if not self.job_id:
            raise JobSpecError("job_id is required")
        if self.requested_gpus < 1:
            raise JobSpecError(f"requested_gpus must be >= 1, got {self.requested_gpus}")
        if not self.output_dir:
            raise JobSpecError("output_dir is required")
        object.__setattr__(
            self, "config_snapshot", MappingProxyType(copy.deepcopy(dict(self.config_snapshot)))
        )

    @property
    def resume(self) -> bool:
        """Whether the configuration snapshot asks to resume a previous run.

        `resume` is a LeRobot train-config key, so it lives inside the snapshot
        rather than as a top-level `JobSpec` field the contract does not list.
        """
        return bool(self.config_snapshot.get("resume", False))


@dataclass
class JobFilter:
    """A list/filter/sort request over the job set (`FR-TRN-027`).

    Attributes:
        states: Keep only jobs in one of these states; empty means all.
        name_contains: Keep only jobs whose name contains this substring.
        sort_by: Field to sort on: "created", "name", or "state".
        descending: Sort direction.
    """

    states: frozenset[JobState] = frozenset()
    name_contains: str = ""
    sort_by: str = "created"
    descending: bool = False

    def matches(self, spec: JobSpec) -> bool:
        """Report whether one job passes this filter's predicates.

        Args:
            spec: The job to test.

        Returns:
            (bool) True when the job satisfies every set predicate.
        """
        if self.states and spec.state not in self.states:
            return False
        return not (self.name_contains and self.name_contains not in spec.name)


_SORT_FIELDS: Mapping[str, Any] = MappingProxyType(
    {
        "created": lambda spec: (spec.created, spec.job_id),
        "name": lambda spec: (spec.name, spec.job_id),
        "state": lambda spec: (spec.state.value, spec.job_id),
    }
)


def apply_filter(specs: list[JobSpec], query: JobFilter) -> list[JobSpec]:
    """Return the jobs matching a filter, in the requested order.

    A stable tie-break on `job_id` is appended to every sort key so the order is
    deterministic when the primary field ties — otherwise a "list jobs" call could
    return two orders for the same data.

    Args:
        specs: The jobs to filter and sort.
        query: The filter and sort request.

    Returns:
        (list[JobSpec]) Matching jobs in sorted order.
    """
    chosen = [spec for spec in specs if query.matches(spec)]
    key = _SORT_FIELDS.get(query.sort_by, _SORT_FIELDS["created"])
    return sorted(chosen, key=key, reverse=query.descending)
