"""Dataset statistics for the OpenArm training corpus (WP-3D-03).

The ten-metric `compute_stats` convention (`mean`/`std`/`min`/`max`/`count` plus
`q01`/`q10`/`q50`/`q90`/`q99`) fit on the TRAIN split only and applied identically to
val/test/inference. LeRobot's `compute_episode_stats`/`aggregate_stats` are CALLED,
not reimplemented; what this band adds is the discipline around them:

- train-split-only normalization with diagnostics kept a distinct type that can never
  be a normalization input (`fit`, `normalize`, `staticcheck` — WP-3D-03 ①);
- standard-deviation-floor detection for stuck `.vel`/`.torque` channels (`stdfloor`,
  WP-3D-03 ③);
- an exact-vs-histogram quantile deviation report (`quantiles`);
- a content hash recorded in lineage and warned on at inference (`hashing`,
  WP-3D-03 ④);
- image [0,1] scaling, which flows through `compute_episode_stats` unchanged.

`pipeline.fit_dataset_statistics` is the single end-to-end entry point.
"""

from __future__ import annotations

from backend.dataset.stats.constants import (
    DIAGNOSTIC_SPLITS,
    IMAGE_NORMALIZED_MAX,
    IMAGE_NORMALIZED_MIN,
    METRIC_KEYS,
    MOMENT_METRIC_KEYS,
    QUANTILE_KEYS,
    QUANTILE_LEVELS,
    SPLIT_NAMES,
    STATS_HASH_ALGORITHM,
    TEST_SPLIT,
    TRAIN_SPLIT,
    VAL_SPLIT,
)
from backend.dataset.stats.episodes import numeric_episode_data, numeric_features, numeric_names
from backend.dataset.stats.fit import (
    DiagnosticStats,
    EpisodeData,
    FittedStats,
    LeakageError,
    NormalizationStats,
    StatsTable,
    compute_diagnostic_stats,
    fit_dataset_stats,
    fit_normalization_stats,
)
from backend.dataset.stats.hashing import (
    stats_content_hash,
    verify_stats_hash,
    warn_on_stats_hash_mismatch,
)
from backend.dataset.stats.normalize import NormalizationMode, Normalizer, build_normalizer
from backend.dataset.stats.pipeline import DatasetStatistics, fit_dataset_statistics
from backend.dataset.stats.quantiles import (
    QuantileDeviation,
    QuantileDeviationReport,
    exact_quantiles,
    quantile_deviation_report,
)
from backend.dataset.stats.staticcheck import scan_source, scan_tree
from backend.dataset.stats.stdfloor import (
    StdFloorReport,
    StdFloorViolation,
    detect_std_floor_violations,
)

__all__ = [
    "DIAGNOSTIC_SPLITS",
    "IMAGE_NORMALIZED_MAX",
    "IMAGE_NORMALIZED_MIN",
    "METRIC_KEYS",
    "MOMENT_METRIC_KEYS",
    "QUANTILE_KEYS",
    "QUANTILE_LEVELS",
    "SPLIT_NAMES",
    "STATS_HASH_ALGORITHM",
    "TEST_SPLIT",
    "TRAIN_SPLIT",
    "VAL_SPLIT",
    "DatasetStatistics",
    "DiagnosticStats",
    "EpisodeData",
    "FittedStats",
    "LeakageError",
    "NormalizationMode",
    "NormalizationStats",
    "Normalizer",
    "QuantileDeviation",
    "QuantileDeviationReport",
    "StatsTable",
    "StdFloorReport",
    "StdFloorViolation",
    "build_normalizer",
    "compute_diagnostic_stats",
    "detect_std_floor_violations",
    "exact_quantiles",
    "fit_dataset_statistics",
    "fit_dataset_stats",
    "fit_normalization_stats",
    "numeric_episode_data",
    "numeric_features",
    "numeric_names",
    "quantile_deviation_report",
    "scan_source",
    "scan_tree",
    "stats_content_hash",
    "verify_stats_hash",
    "warn_on_stats_hash_mismatch",
]
