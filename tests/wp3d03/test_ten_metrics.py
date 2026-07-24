"""WP-3D-03 — the ten `compute_stats` metrics, quantiles included and not optional.

`02b` §8.1 WP-3D-03 fixes the metric set at ten (`mean`/`std`/`min`/`max`/`count`
plus `q01`/`q10`/`q50`/`q90`/`q99`), and §8.2 ② makes the quantiles non-optional
(pi0.5 uses quantiles). A fitted feature carries exactly that set, no more and no
fewer.
"""

from __future__ import annotations

import backend.dataset.stats as stats
from tests.wp3d03 import support


def test_fit_produces_exactly_ten_metrics_per_feature() -> None:
    """Each fitted feature carries exactly the ten-metric set."""
    feats = support.features()
    result = stats.fit_normalization_stats(support.episode_generator(3), feats)

    assert set(result.per_feature) == set(feats)
    assert len(stats.METRIC_KEYS) == 10
    for metrics in result.per_feature.values():
        assert set(metrics) == set(stats.METRIC_KEYS)


def test_quantiles_are_present_and_not_optional() -> None:
    """q01..q99 are always present — the pi0.5 quantile requirement (WP-3D-03 ②)."""
    feats = support.features()
    result = stats.fit_normalization_stats(support.episode_generator(3), feats)

    assert stats.QUANTILE_KEYS == ("q01", "q10", "q50", "q90", "q99")
    for metrics in result.per_feature.values():
        for quantile_key in stats.QUANTILE_KEYS:
            assert quantile_key in metrics


def test_quantile_levels_match_the_compute_stats_convention() -> None:
    """The quantile levels are LeRobot's `DEFAULT_QUANTILES`, not a local restatement."""
    from lerobot.datasets.compute_stats import DEFAULT_QUANTILES

    assert tuple(DEFAULT_QUANTILES) == stats.QUANTILE_LEVELS


def test_count_reflects_total_train_frames() -> None:
    """The `count` metric aggregates to the total frames fit over."""
    feats = support.features()
    episodes = [support.episode(index, frames=10) for index in range(4)]
    result = stats.fit_normalization_stats(iter(episodes), feats)

    assert result.episode_count == 4
    assert result.frame_count == 40
    for metrics in result.per_feature.values():
        assert int(metrics["count"].reshape(-1)[0]) == 40
