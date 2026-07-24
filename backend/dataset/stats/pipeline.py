"""End-to-end dataset statistics: fit train-only, build the normalizer, hash it.

This wires the band's parts in the one correct order — fit normalization on the
train split, build the normalizer from that train statistic (never a diagnostic),
and content-hash it for lineage — so a caller (the GUI liaison WP-3D-08, the lineage
DB WP-3D-04) has a single entry point that cannot take the leakage path. It is also
the owned tree's one real `build_normalizer` call site, which is what keeps the
`staticcheck` non-vacuous: the argument here is the train normalization, so the scan
passes on real code and only a diagnostic argument would fail it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from backend.dataset.stats.fit import EpisodeData, FittedStats, fit_dataset_stats
from backend.dataset.stats.hashing import stats_content_hash
from backend.dataset.stats.normalize import NormalizationMode, Normalizer, build_normalizer


@dataclass(frozen=True)
class DatasetStatistics:
    """A dataset's fitted statistics, the train-derived normalizer, and the content hash.

    Attributes:
        fitted: Train normalization plus per-split diagnostics.
        normalizer: The normalizer built from the TRAIN normalization statistics.
        content_hash: The stats content hash recorded in the lineage record/checkpoint.
    """

    fitted: FittedStats
    normalizer: Normalizer
    content_hash: str


def fit_dataset_statistics(
    episodes_by_split: Mapping[str, Iterable[EpisodeData]],
    features: Mapping[str, object],
    mode: NormalizationMode = NormalizationMode.MEAN_STD,
) -> DatasetStatistics:
    """Fit a dataset's statistics and build its normalizer from the train split only.

    Args:
        episodes_by_split: Split name to per-episode inputs; must contain the train split.
        features: The shared `features` description.
        mode: The normalization mode for the normalizer.

    Returns:
        (DatasetStatistics) The fitted stats, the train-derived normalizer, and the hash.
    """
    fitted = fit_dataset_stats(episodes_by_split, features)
    normalizer = build_normalizer(fitted.normalization, mode)
    content_hash = stats_content_hash(fitted.normalization)
    return DatasetStatistics(fitted=fitted, normalizer=normalizer, content_hash=content_hash)
