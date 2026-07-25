"""The success-rate aggregator and the checkpoint comparison guard (`02c` §3.3).

`aggregate` turns a set of `EpisodeRecord`s for one (rollout set, checkpoint) into
a `SuccessRateReport`: point estimate, the canonical Wilson 95% interval, the
boundary-only Clopper-Pearson interval, the `FR-SIM-058`+`NFR-PRF-050` metrics,
and the generic failure-tag tally. It is a pure consumer of labels — it never
invents a `success` — so it runs offline whether or not auto-labelling (§3.7) is
on, which is exactly why WP-4C-03 is decoupled from it (`02c` §3.3 워크플로우 형상).

`compare_checkpoints` is the load-bearing negative space. `FR-INF-063` forbids
ranking two checkpoints from a SINGLE execution of a rollout set (nondeterministic
augmentation alone swings success 5-6%p), so there is deliberately NO code path
that takes one report per side and returns an order:

- it requires `MIN_INDEPENDENT_RUNS` (>=2) independent runs per checkpoint, else
  UNDETERMINED / single-run (CG-4C-03e);
- it requires every run to be statistically meaningful (N>=20), else UNDETERMINED
  / meaningless (CG-4C-03c);
- it ranks only when the pooled Wilson intervals are DISJOINT; overlapping
  intervals return UNDETERMINED (우열 미판정), because ranking overlapping
  intervals is ranking noise (CG-4C-06d).

The comparison claims no separate confidence interval on the *difference* of two
proportions: the spec grounds no such statistic, so — as with §3.5's generalization
gap — the plan does not invent one. It compares each checkpoint's own Wilson CI.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from backend.eval.stats.constants import (
    LATENCY_PERCENTILE,
    MIN_INDEPENDENT_RUNS,
    N_MIN_MEANINGFUL,
    REASON_CI_SEPARATED,
    REASON_NOT_MEANINGFUL,
    REASON_OVERLAPPING_CI,
    REASON_SINGLE_RUN,
    SELF_BASELINE_KIND,
    VERDICT_A_BETTER,
    VERDICT_B_BETTER,
    VERDICT_UNDETERMINED,
)
from backend.eval.stats.episode import EpisodeRecord
from backend.eval.stats.intervals import (
    ConfidenceInterval,
    clopper_pearson_boundary_interval,
    is_boundary,
    wilson_interval,
)
from backend.eval.stats.report import SuccessRateReport

# WP-4A-05 lineage consumption: a report is aggregated FOR a lineage `CheckpointId`,
# passed in as the grouping context. This import (with report.py's) backs the
# WP-4A-05 -> WP-4C-03 reference edge (`06` §5.6 / CI-16).
from backend.training.lineage import CheckpointId


class AggregationError(ValueError):
    """Raised when aggregation input cannot form a report.

    Cases: an empty episode set (no proportion), or a comparison whose two runs on
    one side name different checkpoints (then it is not a two-checkpoint comparison).
    """


def aggregate(
    rollout_set_id: str,
    checkpoint: CheckpointId,
    episodes: Sequence[EpisodeRecord],
) -> SuccessRateReport:
    """Aggregate one (rollout set, checkpoint)'s episodes into a `SuccessRateReport`.

    Args:
        rollout_set_id: The rollout set the episodes belong to.
        checkpoint: The WP-4A-05 lineage identity of the evaluated checkpoint.
        episodes: The episodes to aggregate; must be non-empty and each valid.

    Returns:
        (SuccessRateReport) The report, with Wilson always and Clopper-Pearson
            only on the p̂∈{0,1} boundary.

    Raises:
        AggregationError: When `episodes` is empty.
        EpisodeRecordError: When an episode is internally inconsistent.
    """
    if not episodes:
        raise AggregationError(
            "cannot aggregate an empty episode set — a success rate needs at least one trial "
            f"(rollout_set_id={rollout_set_id!r})"
        )
    for episode in episodes:
        episode.validate()

    n_trials = len(episodes)
    n_success = sum(1 for episode in episodes if episode.success)
    point_estimate = n_success / n_trials

    wilson = wilson_interval(n_success, n_trials)
    clopper_pearson: ConfidenceInterval | None = (
        clopper_pearson_boundary_interval(n_success, n_trials)
        if is_boundary(n_success, n_trials)
        else None
    )

    lengths = [episode.episode_length for episode in episodes]
    latency_p95s = [episode.inference_latency_p95 for episode in episodes]
    tag_counts: Counter[str] = Counter(tag for episode in episodes for tag in episode.failure_tags)

    report = SuccessRateReport(
        rollout_set_id=rollout_set_id,
        checkpoint=checkpoint,
        n_trials=n_trials,
        n_success=n_success,
        point_estimate=point_estimate,
        ci_wilson_95=wilson,
        ci_clopper_pearson_95=clopper_pearson,
        statistically_meaningful=n_trials >= N_MIN_MEANINGFUL,
        seeds=tuple(episode.seed for episode in episodes),
        episode_length_median=float(np.median(lengths)),
        collision_count=sum(episode.collisions for episode in episodes),
        torque_limit_hits=sum(episode.torque_limit_hits for episode in episodes),
        safety_stop_count=sum(episode.safety_stops for episode in episodes),
        inference_latency_p95=float(np.percentile(latency_p95s, LATENCY_PERCENTILE)),
        failure_tag_counts=dict(tag_counts),
        baseline_kind=SELF_BASELINE_KIND,
    )
    report.validate()
    return report


@dataclass(frozen=True)
class CheckpointComparison:
    """The outcome of comparing two checkpoints' repeated rollout sets.

    `verdict` is only an ordered value (`VERDICT_A_BETTER` / `VERDICT_B_BETTER`)
    when the interval evidence separates the checkpoints; every ineligible or
    ambiguous case is `VERDICT_UNDETERMINED` with a `reason` distinguishing
    "not enough runs" (single-run), "sample too small" (N<20), and "runs agree
    within noise" (overlapping CI).

    Attributes:
        checkpoint_a: The first checkpoint's lineage identity.
        checkpoint_b: The second checkpoint's lineage identity.
        verdict: One of the three `VERDICT_*` values.
        reason: Why this verdict — one of the `REASON_*` messages.
        pooled_ci_a: A's pooled Wilson interval, or `None` when comparison was
            refused before pooling (single-run / meaningless).
        pooled_ci_b: B's pooled Wilson interval, or `None`, symmetrically.
    """

    checkpoint_a: CheckpointId
    checkpoint_b: CheckpointId
    verdict: str
    reason: str
    pooled_ci_a: ConfidenceInterval | None
    pooled_ci_b: ConfidenceInterval | None

    @property
    def is_ranked(self) -> bool:
        """Whether the comparison produced an ordering (never true for a single run)."""
        return self.verdict in (VERDICT_A_BETTER, VERDICT_B_BETTER)


def compare_checkpoints(
    runs_a: Sequence[SuccessRateReport],
    runs_b: Sequence[SuccessRateReport],
) -> CheckpointComparison:
    """Compare two checkpoints from their repeated rollout sets (`FR-INF-063`).

    There is no single-report overload of this function on purpose: ranking from a
    single execution is what `FR-INF-063` forbids, so the only comparison entry
    point requires a sequence of independent runs per side and refuses to rank
    fewer than `MIN_INDEPENDENT_RUNS`.

    Args:
        runs_a: Independent runs of checkpoint A (repeats of its rollout set).
        runs_b: Independent runs of checkpoint B.

    Returns:
        (CheckpointComparison) An ordered verdict only when both sides have enough
            meaningful runs and their pooled Wilson intervals are disjoint;
            UNDETERMINED otherwise, with the reason.

    Raises:
        AggregationError: When a side's runs name more than one checkpoint (then it
            is not a two-checkpoint comparison).
    """
    checkpoint_a = _sole_checkpoint(runs_a, "runs_a")
    checkpoint_b = _sole_checkpoint(runs_b, "runs_b")

    if len(runs_a) < MIN_INDEPENDENT_RUNS or len(runs_b) < MIN_INDEPENDENT_RUNS:
        return _undetermined(checkpoint_a, checkpoint_b, REASON_SINGLE_RUN)

    if not _all_meaningful(runs_a) or not _all_meaningful(runs_b):
        return _undetermined(checkpoint_a, checkpoint_b, REASON_NOT_MEANINGFUL)

    pooled_a = _pool_wilson(runs_a)
    pooled_b = _pool_wilson(runs_b)
    if pooled_a.overlaps(pooled_b):
        return CheckpointComparison(
            checkpoint_a=checkpoint_a,
            checkpoint_b=checkpoint_b,
            verdict=VERDICT_UNDETERMINED,
            reason=REASON_OVERLAPPING_CI,
            pooled_ci_a=pooled_a,
            pooled_ci_b=pooled_b,
        )

    a_is_higher = _pooled_point(runs_a) > _pooled_point(runs_b)
    return CheckpointComparison(
        checkpoint_a=checkpoint_a,
        checkpoint_b=checkpoint_b,
        verdict=VERDICT_A_BETTER if a_is_higher else VERDICT_B_BETTER,
        reason=REASON_CI_SEPARATED,
        pooled_ci_a=pooled_a,
        pooled_ci_b=pooled_b,
    )


def _sole_checkpoint(runs: Sequence[SuccessRateReport], label: str) -> CheckpointId:
    """Return the single checkpoint a side's runs share, or refuse a mixed side.

    A side of the comparison is repeats of ONE checkpoint. If its runs name several
    checkpoints the input is not a two-checkpoint comparison and is refused rather
    than silently pooled across checkpoints.
    """
    if not runs:
        raise AggregationError(f"{label} is empty; a comparison side needs at least one run")
    checkpoints = {run.checkpoint for run in runs}
    if len(checkpoints) != 1:
        raise AggregationError(
            f"{label} mixes {len(checkpoints)} checkpoints; a comparison side must be repeats of "
            "one checkpoint"
        )
    return next(iter(checkpoints))


def _all_meaningful(runs: Sequence[SuccessRateReport]) -> bool:
    """Whether every run cleared the N>=20 meaningfulness threshold."""
    return all(run.statistically_meaningful for run in runs)


def _pool_wilson(runs: Sequence[SuccessRateReport]) -> ConfidenceInterval:
    """Pool a checkpoint's independent runs into one Wilson interval.

    The repeats target the same checkpoint and rollout set, differing only in
    nondeterministic augmentation, so their binomial trials pool into one larger
    sample — more trials, a tighter interval. This models the 5-6%p swing as
    within-binomial spread; a separate between-run variance term would be a
    statistic the spec does not ground, so the plan does not add one (`02c` §3.3).
    """
    n_success = sum(run.n_success for run in runs)
    n_trials = sum(run.n_trials for run in runs)
    return wilson_interval(n_success, n_trials)


def _pooled_point(runs: Sequence[SuccessRateReport]) -> float:
    """The pooled point estimate across a checkpoint's runs."""
    n_success = sum(run.n_success for run in runs)
    n_trials = sum(run.n_trials for run in runs)
    return n_success / n_trials


def _undetermined(
    checkpoint_a: CheckpointId, checkpoint_b: CheckpointId, reason: str
) -> CheckpointComparison:
    """Build an UNDETERMINED comparison refused before pooling."""
    return CheckpointComparison(
        checkpoint_a=checkpoint_a,
        checkpoint_b=checkpoint_b,
        verdict=VERDICT_UNDETERMINED,
        reason=reason,
        pooled_ci_a=None,
        pooled_ci_b=None,
    )
