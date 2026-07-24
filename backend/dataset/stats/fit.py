"""Fit dataset normalization statistics on the TRAIN split only (WP-3D-03).

The ten metrics (`mean`/`std`/`min`/`max`/`count` plus `q01`/`q10`/`q50`/`q90`/`q99`)
come from LeRobot's `compute_episode_stats`/`aggregate_stats` — this band CALLS that
convention, it does not reimplement it. Two rules the plan makes load-bearing are
enforced here by construction:

- TRAIN-SPLIT-ONLY FIT. Normalization statistics are produced only from the train
  split and applied identically to val/test/inference. A per-split re-fit is
  validation leakage and FAIL_BLOCKING (`02b` §8.2 WP-3D-03), so a non-train split
  can never yield a `NormalizationStats`: it yields a `DiagnosticStats`, a distinct
  type the normalizer refuses (`normalize.build_normalizer`), and `staticcheck`
  additionally forbids a diagnostic value from reaching a normalization input.

- STREAMING AGGREGATION. Episodes are folded one at a time — `compute_episode_stats`
  per episode, then `aggregate_stats([running, episode])` — so peak memory is bounded
  by a single episode plus the O(dim) running aggregate, independent of the episode
  count. Count-weighted aggregation is associative, so the incremental fold is
  numerically identical to aggregating the whole list at once, while retaining O(1)
  state rather than O(episodes) (`02b` §8.2 WP-3D-03 ⑤: proportional growth =
  streaming not implemented = a regression).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import numpy as np
from lerobot.datasets.compute_stats import aggregate_stats, compute_episode_stats

from backend.dataset.stats.constants import QUANTILE_LEVELS, TRAIN_SPLIT

# A per-feature statistics table: feature key -> metric key -> value array.
StatsTable = dict[str, dict[str, np.ndarray]]
# One episode's `compute_episode_stats` input: feature key -> numpy array or path list.
EpisodeData = Mapping[str, object]


class LeakageError(ValueError):
    """Raised when a normalization fit is attempted on anything but the train split.

    Fitting normalization on val/test — or re-fitting per split — leaks the
    evaluation distribution into training. `02b` §8.2 WP-3D-03 makes this
    FAIL_BLOCKING; the fit refuses it rather than producing a leaked statistic.
    """


@dataclass(frozen=True)
class NormalizationStats:
    """Normalization statistics fit on the TRAIN split — the only stats a normalizer may use.

    Attributes:
        per_feature: Feature key to its ten-metric table.
        episode_count: Train episodes folded in.
        frame_count: Train frames the statistics were fit over.
    """

    per_feature: StatsTable
    episode_count: int
    frame_count: int


@dataclass(frozen=True)
class DiagnosticStats:
    """Split-local statistics for a non-train split — DIAGNOSTIC ONLY.

    Deliberately not a `NormalizationStats`: a diagnostic value can never be passed
    where a normalization input is expected (WP-3D-03 ①). It exists so an operator
    can SEE how a val/test distribution differs from train, which is expected and not
    a defect (`02b` §8.3: the diagnostic screen keeps reporting the distributions
    differ, and that is correct behaviour, not a fault).

    Attributes:
        split: The split these describe (`val`/`test`).
        per_feature: Feature key to its ten-metric table.
        episode_count: Episodes folded in.
        frame_count: Frames described.
    """

    split: str
    per_feature: StatsTable
    episode_count: int
    frame_count: int


@dataclass(frozen=True)
class FittedStats:
    """A dataset's fitted normalization plus its per-split diagnostics.

    Attributes:
        normalization: The train-only normalization statistics (the sole normalizer input).
        diagnostics: Split name to its diagnostic statistics, for val/test.
    """

    normalization: NormalizationStats
    diagnostics: dict[str, DiagnosticStats]


def _frame_count(table: StatsTable) -> int:
    """Return the frames a stats table was fit over, read from any feature's count."""
    for metrics in table.values():
        return int(np.asarray(metrics["count"]).reshape(-1)[0])
    return 0


def _stream_aggregate(
    episodes: Iterable[EpisodeData], features: Mapping[str, object]
) -> tuple[StatsTable, int]:
    """Fold episodes into one aggregate table, one episode alive at a time.

    The iterable is consumed lazily and each episode's per-episode statistics are
    folded into the running aggregate immediately, so at most one episode's data and
    the O(dim) running aggregate are held at once — never the whole set.

    Args:
        episodes: An iterable of per-episode `compute_episode_stats` inputs.
        features: The `features` description for every key an episode carries.

    Returns:
        (tuple) The aggregated ten-metric table and the episode count.

    Raises:
        ValueError: When the iterable yields no episode.
    """
    running: StatsTable | None = None
    count = 0
    quantiles = list(QUANTILE_LEVELS)
    for episode in episodes:
        episode_stats = compute_episode_stats(
            dict(episode), dict(features), quantile_list=quantiles
        )
        running = episode_stats if running is None else aggregate_stats([running, episode_stats])
        count += 1
    if running is None:
        raise ValueError("no episodes to aggregate")
    return running, count


def fit_normalization_stats(
    train_episodes: Iterable[EpisodeData],
    features: Mapping[str, object],
    split: str = TRAIN_SPLIT,
) -> NormalizationStats:
    """Fit normalization statistics over the train split, streaming one episode at a time.

    Args:
        train_episodes: The train split's per-episode inputs.
        features: The `features` description.
        split: The split being fit; anything but the train split is refused as leakage.

    Returns:
        (NormalizationStats) The train-only statistics applied to every split.

    Raises:
        LeakageError: When `split` is not the train split.
    """
    if split != TRAIN_SPLIT:
        raise LeakageError(
            f"normalization must fit on {TRAIN_SPLIT!r}, not {split!r}: "
            "a per-split re-fit leaks the evaluation distribution (02b §8.2 WP-3D-03)"
        )
    table, episodes = _stream_aggregate(train_episodes, features)
    return NormalizationStats(
        per_feature=table, episode_count=episodes, frame_count=_frame_count(table)
    )


def compute_diagnostic_stats(
    episodes: Iterable[EpisodeData],
    features: Mapping[str, object],
    split: str,
) -> DiagnosticStats:
    """Compute split-local DIAGNOSTIC statistics for a non-train split.

    These describe how a split's distribution differs from train; they are never a
    normalization input (WP-3D-03 ①). Refuses the train split, which normalizes and
    must go through `fit_normalization_stats`.

    Args:
        episodes: The split's per-episode inputs.
        features: The `features` description.
        split: The non-train split (`val`/`test`).

    Returns:
        (DiagnosticStats) Diagnostic-only statistics for the split.

    Raises:
        LeakageError: When `split` is the train split.
    """
    if split == TRAIN_SPLIT:
        raise LeakageError(
            f"{TRAIN_SPLIT!r} is normalized, not diagnostic; use fit_normalization_stats"
        )
    table, count = _stream_aggregate(episodes, features)
    return DiagnosticStats(
        split=split, per_feature=table, episode_count=count, frame_count=_frame_count(table)
    )


def fit_dataset_stats(
    episodes_by_split: Mapping[str, Iterable[EpisodeData]],
    features: Mapping[str, object],
) -> FittedStats:
    """Fit train-only normalization and per-split diagnostics for a dataset.

    Normalization is fit ONLY from `episodes_by_split[train]`; every other split
    yields diagnostics. There is no path by which a non-train split contributes to
    normalization, so the leakage the plan forbids is impossible by construction.

    Args:
        episodes_by_split: Split name to its per-episode inputs. Must contain the train split.
        features: The `features` description shared across splits.

    Returns:
        (FittedStats) Train normalization plus val/test diagnostics.

    Raises:
        KeyError: When no train split is supplied.
    """
    if TRAIN_SPLIT not in episodes_by_split:
        raise KeyError(f"no {TRAIN_SPLIT!r} split to fit normalization on")
    normalization = fit_normalization_stats(episodes_by_split[TRAIN_SPLIT], features)
    diagnostics: dict[str, DiagnosticStats] = {}
    for split, episodes in episodes_by_split.items():
        if split == TRAIN_SPLIT:
            continue
        diagnostics[split] = compute_diagnostic_stats(episodes, features, split)
    return FittedStats(normalization=normalization, diagnostics=diagnostics)
