"""Named constants for the WP-3D-03 dataset-statistics band (`02b` §8.1/§8.2).

The quantile levels are LeRobot's `DEFAULT_QUANTILES`, imported rather than
restated so the ten-metric set stays identical to the `compute_stats` convention
this band is required to follow (`02b` §8.2 WP-3D-03 ②: `q01`/`q99` are not
optional — pi0.5 uses quantiles). The standard-deviation floor is deliberately
absent: `02b` §8.2 WP-3D-03 fixes it as decision-needed, measured then
regression-locked, so a caller supplies it and this module names no target — the
same stance the recorder quality band takes for its provisional thresholds.
"""

from __future__ import annotations

from lerobot.datasets.compute_stats import DEFAULT_QUANTILES

# The three dataset splits. Statistics fit on the TRAIN split only and apply
# identically to val/test/inference; a per-split re-fit is validation leakage and
# FAIL_BLOCKING (`02b` §8.2 WP-3D-03).
TRAIN_SPLIT = "train"
VAL_SPLIT = "val"
TEST_SPLIT = "test"
SPLIT_NAMES = (TRAIN_SPLIT, VAL_SPLIT, TEST_SPLIT)
# The non-train splits whose statistics are DIAGNOSTIC ONLY — never a
# normalization input (WP-3D-03 ①, enforced by the type split plus `staticcheck`).
DIAGNOSTIC_SPLITS = (VAL_SPLIT, TEST_SPLIT)

# The quantile levels and their metric keys, from the `compute_stats` convention.
# `q{int(level * 100):02d}` matches LeRobot's key spelling exactly, so the keys are
# `q01`/`q10`/`q50`/`q90`/`q99`.
QUANTILE_LEVELS = tuple(DEFAULT_QUANTILES)
QUANTILE_KEYS = tuple(f"q{int(level * 100):02d}" for level in QUANTILE_LEVELS)
# The five moment/extent metrics plus the five quantiles: the ten metrics a fitted
# feature carries (`02b` §8.1 WP-3D-03).
MOMENT_METRIC_KEYS = ("mean", "std", "min", "max", "count")
METRIC_KEYS = MOMENT_METRIC_KEYS + QUANTILE_KEYS

# RGB image statistics land in [0, 1]: `compute_episode_stats` divides an RGB
# channel by 255, and a depth map (a feature flagged `is_depth_map`) keeps its
# stored units. The 255 factor is LeRobot's and is not restated here; these are the
# image [0,1]-scaling bounds the band asserts (`02b` §8.1 WP-3D-03).
IMAGE_NORMALIZED_MIN = 0.0
IMAGE_NORMALIZED_MAX = 1.0

# The stats content hash recorded in the lineage record and the checkpoint (`02b`
# §8.1 WP-3D-04 consumes it; §8.2 WP-3D-03 ④: a mismatch warns at inference).
# SHA-256 over a canonical float64 serialization so the digest is stable across the
# platforms a checkpoint travels between.
STATS_HASH_ALGORITHM = "sha256"
