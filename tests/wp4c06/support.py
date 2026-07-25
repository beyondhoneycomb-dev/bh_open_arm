"""Synthetic fixtures for the WP-4C-06 selection tests.

The real rollout/label population (WP-4C-01/02) is DEFERRED, so these build
`SuccessRateReport`s from fabricated episode outcomes with a chosen success count —
never a real rollout number. They exist to exercise the offline selection policy:
given chosen (n_success, n_trials) per checkpoint, assemble scorecards so the
CI-based selection rule, the render invariants, and the static checks can be
verified against known inputs.
"""

from __future__ import annotations

from backend.eval.selection import (
    CONDITION_NOMINAL,
    CheckpointScorecard,
    FrequencyConfig,
    OfflineMetrics,
    PerTaskReport,
    ScorecardTable,
)
from backend.eval.stats import SuccessRateReport, aggregate
from backend.eval.stats.episode import EpisodeRecord
from backend.training.lineage import CheckpointId

DEFAULT_FREQ = FrequencyConfig(log_freq=10, save_freq=1000, eval_steps=500, env_eval_freq=2000)
DEFAULT_METRICS = OfflineMetrics(val_loss=0.1, action_mse=0.02)
DEFAULT_TASK = "pick"


def checkpoint(output_dir: str = "/runs/a", step: int = 1000) -> CheckpointId:
    """A WP-4A-05 lineage checkpoint identity."""
    return CheckpointId(output_dir=output_dir, step=step)


def episodes(
    n_success: int, n_trials: int, seed0: int = 0, task: str = DEFAULT_TASK
) -> list[EpisodeRecord]:
    """Build `n_trials` synthetic episodes with exactly `n_success` successes."""
    return [
        EpisodeRecord(
            task_id=task,
            seed=seed0 + index,
            success=index < n_success,
            episode_length=100,
            collisions=0 if index < n_success else 1,
            torque_limit_hits=0,
            safety_stops=0 if index < n_success else 1,
            inference_latency_p95=10.0,
            failure_tags=() if index < n_success else ("COLLISION",),
        )
        for index in range(n_trials)
    ]


def report(
    ckpt: CheckpointId,
    n_success: int,
    n_trials: int,
    seed0: int = 0,
    task: str = DEFAULT_TASK,
    rollout_set_id: str = "rs",
) -> SuccessRateReport:
    """Aggregate a synthetic (n_success, n_trials) into a `SuccessRateReport`."""
    return aggregate(rollout_set_id, ckpt, episodes(n_success, n_trials, seed0, task))


def scorecard(
    ckpt: CheckpointId,
    n_success: int,
    n_trials: int,
    seed0: int = 0,
    condition: str = CONDITION_NOMINAL,
    task: str = DEFAULT_TASK,
    metrics: OfflineMetrics = DEFAULT_METRICS,
    frequencies: FrequencyConfig = DEFAULT_FREQ,
) -> CheckpointScorecard:
    """A single-(task, condition) scorecard for one checkpoint."""
    return CheckpointScorecard(
        checkpoint=ckpt,
        lineage_ref=f"{ckpt.output_dir}@{ckpt.step}",
        per_task=(PerTaskReport(task, condition, report(ckpt, n_success, n_trials, seed0, task)),),
        offline_metrics=metrics,
        frequencies=frequencies,
    )


def table_of(*scorecards: CheckpointScorecard) -> ScorecardTable:
    """A `ScorecardTable` accumulating the given scorecards in order."""
    table = ScorecardTable()
    for card in scorecards:
        table.add(card)
    return table
