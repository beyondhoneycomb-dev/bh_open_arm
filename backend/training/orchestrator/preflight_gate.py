"""The per-job inputs the orchestrator's PREFLIGHT state feeds to the WP-4A gate.

WP-4A-01 owns the launch path but not the checkers: preflight (WP-4A-02), the
degeneracy gate (WP-4A-03), and lineage (WP-4A-05) are committed upstream and are
imported, never forked. What was missing (OBS-1) is the wiring — the orchestrator's
PREFLIGHT state was a pass-through, so a job could reach RUNNING without preflight
ever running or a `TrainingClearance` ever being obtained. This module carries the
two collaborator shapes that close that gap:

- `PreflightProvider` resolves, for one `JobSpec`, the dataset/policy the checker
  needs plus any already-detected degenerate findings. The orchestrator cannot
  synthesise a dataset description from a `JobSpec` (which is FR-TRN-027 and nothing
  more), so the description is supplied, not invented — a `BLOCK`-ing dataset is a
  `BLOCK`-ing input, never a fabricated pass.
- `LaunchLineagePlanner` assembles the WP-4A-05 `LineageRecord` recorded on launch.
  Element (c) (session merge history / episodes) and element (a) (`stats_hash`) are
  facts a `JobSpec` does not carry, so the record is built by a collaborator that
  owns those facts; the orchestrator only drives it. The `TrainingClearance` is
  handed in so the planner can read its degenerate decisions into element (h).

Neither shape is a checker. The gate — preflight PASS plus a clearance minted by
`clear_for_training` — is enforced in the orchestrator itself, so these providers
cannot weaken it: the worst a provider can do is describe a clean dataset, which
still passes through the real `preflight`/`clear_for_training`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.training.degenerate import (
    DegenerateDecision,
    DegenerateFinding,
    TrainingClearance,
)
from backend.training.lineage import CheckpointId, LineageRecord
from backend.training.orchestrator.spec import JobSpec
from backend.training.preflight import (
    DatasetPreflightInput,
    PolicyPreflightSpec,
    PreflightReport,
)


@dataclass(frozen=True)
class PreflightContext:
    """Everything the PREFLIGHT gate needs to judge one job.

    Attributes:
        dataset: The dataset described by its `meta/info.json` / `meta/stats.json`
            maps — the input WP-4A-02 `preflight` runs over.
        policy: The policy the dataset will train, judged by its declared
            normalization/rename behaviour (never its name).
        degenerate_findings: The WP-4A-03 findings already detected for this dataset
            (empty when none); every one must carry a decision before a clearance is
            minted (`FR-TRN-068`).
        initial_decisions: Decisions supplied up front — a job whose findings are all
            pre-decided clears without waiting; the rest arrive through `decide`.
    """

    dataset: DatasetPreflightInput
    policy: PolicyPreflightSpec
    degenerate_findings: tuple[DegenerateFinding, ...] = ()
    initial_decisions: tuple[DegenerateDecision, ...] = ()


class PreflightProvider(Protocol):
    """Resolves the PREFLIGHT gate input for a job from its spec.

    Ownership: the orchestrator holds one provider and calls `context_for` on the
    scheduler thread while dispatching a job, so an implementation must be cheap —
    precomputed or a fast lookup, not heavy in-line I/O under the scheduler lock.
    """

    def context_for(self, spec: JobSpec) -> PreflightContext:
        """Return the preflight context for one job.

        Args:
            spec: The job about to be preflighted.

        Returns:
            (PreflightContext) The dataset/policy and any degenerate findings.
        """
        ...


@dataclass(frozen=True)
class LaunchLineage:
    """The WP-4A-05 lineage to record for a run at the moment it launches.

    Attributes:
        record: The eight-element `FR-TRN-054` snapshot (built, not yet written).
        checkpoint: The checkpoint identity the snapshot attaches to.
        dataset_content_hash: The reverse-index key (WP-3D-03), outside the snapshot.
    """

    record: LineageRecord
    checkpoint: CheckpointId
    dataset_content_hash: str


class LaunchLineagePlanner(Protocol):
    """Assembles the launch-time `LineageRecord` for a cleared job.

    Ownership: held by the orchestrator and called inside the launch path, after the
    clearance is minted and before the monitor starts. Returning `None` means "no
    lineage to record for this run", which the orchestrator treats as a no-op rather
    than a launch failure.
    """

    def plan(self, spec: JobSpec, clearance: TrainingClearance) -> LaunchLineage | None:
        """Build the lineage to record for a launching run.

        Args:
            spec: The job being launched.
            clearance: The minted clearance; its `decisions` are element (h).

        Returns:
            (LaunchLineage | None) The record/checkpoint/hash to write, or None.
        """
        ...


@dataclass
class GateState:
    """The mutable PREFLIGHT-gate bookkeeping a job accrues, kept off `JobSpec`.

    `JobSpec` is FR-TRN-027 verbatim and carries none of this; it lives on the
    runtime record instead. A job holds one `GateState` from the moment its context
    is resolved until it launches or is rejected.

    Attributes:
        context: The resolved preflight input, or None before resolution.
        report: The WP-4A-02 verdict once `preflight` has run; its `findings` are the
            BLOCK findings, attached so a rejection is actionable.
        degenerate_findings: The WP-4A-03 findings under three-way review (from the
            context), each of which must be decided before a clearance is minted.
        decisions: The three-way decisions recorded so far (initial + via `decide`).
        awaiting_decisions: True while the job is parked in PREFLIGHT holding its GPU
            because a degenerate finding still has no decision (`FR-TRN-068`).
        clearance: The minted `TrainingClearance` once the job is cleared, else None.
    """

    context: PreflightContext | None = None
    report: PreflightReport | None = None
    degenerate_findings: tuple[DegenerateFinding, ...] = ()
    decisions: tuple[DegenerateDecision, ...] = ()
    awaiting_decisions: bool = False
    clearance: TrainingClearance | None = None
