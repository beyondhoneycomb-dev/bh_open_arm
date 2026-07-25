"""WP-4C-03 — the success-rate statistics aggregator (Wilson + Clopper-Pearson).

`02c` §3.3. This package turns labelled episode outcomes into success-rate reports
with the correct confidence intervals, and it enforces the protocol's load-bearing
invariants in code rather than by convention:

- **Wilson is canonical; Clopper-Pearson is the boundary companion.** Every report
  carries the Wilson 95% interval; the exact Clopper-Pearson interval is added only
  when `n_success ∈ {0, n_trials}`, where Wilson collapses (`intervals`).
- **N>=20 is the only meaningfulness rule.** `statistically_meaningful` is exactly
  `n_trials >= 20`; below it the report is flagged and no ranking is issued
  (`report`, `aggregator`).
- **No single-run ranking.** The only checkpoint-comparison entry point requires
  >=2 independent runs per side and refuses to order overlapping Wilson intervals
  (`aggregator.compare_checkpoints`, `FR-INF-063`).
- **Self-baseline only.** `baseline_kind` is fixed; there is no field for an
  external baseline (`report`, `FR-SIM-059`).

It is a pure consumer of WP-4C-02 labels and WP-4A-05 lineage: it never invents a
`success` or a rollout number. The real rollout population (WP-4C-01/02) is
DEFERRED; this package is exercised on synthetic outcomes.
"""

from __future__ import annotations

from backend.eval.stats.aggregator import (
    AggregationError,
    CheckpointComparison,
    aggregate,
    compare_checkpoints,
)
from backend.eval.stats.constants import (
    FR_SIM_058_ITEMS,
    MIN_INDEPENDENT_RUNS,
    N_MIN_MEANINGFUL,
    NFR_PRF_050_ITEMS,
    SELF_BASELINE_KIND,
    VERDICT_A_BETTER,
    VERDICT_B_BETTER,
    VERDICT_UNDETERMINED,
    Z_SCORE_95,
)
from backend.eval.stats.episode import EpisodeRecord, EpisodeRecordError
from backend.eval.stats.intervals import (
    ConfidenceInterval,
    IntervalError,
    clopper_pearson_boundary_interval,
    is_boundary,
    wilson_interval,
)
from backend.eval.stats.report import SuccessRateReport, SuccessRateReportError

__all__ = [
    "FR_SIM_058_ITEMS",
    "MIN_INDEPENDENT_RUNS",
    "NFR_PRF_050_ITEMS",
    "N_MIN_MEANINGFUL",
    "SELF_BASELINE_KIND",
    "VERDICT_A_BETTER",
    "VERDICT_B_BETTER",
    "VERDICT_UNDETERMINED",
    "Z_SCORE_95",
    "AggregationError",
    "CheckpointComparison",
    "ConfidenceInterval",
    "EpisodeRecord",
    "EpisodeRecordError",
    "IntervalError",
    "SuccessRateReport",
    "SuccessRateReportError",
    "aggregate",
    "clopper_pearson_boundary_interval",
    "compare_checkpoints",
    "is_boundary",
    "wilson_interval",
]
