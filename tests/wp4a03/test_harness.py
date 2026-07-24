"""The σ_min/δ_min derivation harness derives a threshold or declines — never invents.

`02c` §1.3 σ_min block: the plan does not pin σ_min. The harness must (a) place a
threshold at the valley when the degenerate and normal clusters separate, recording
the rationale, and (b) ABANDON auto-derivation when they do not, deferring to
showing every channel. Both branches are proved here, and every derivation is
stamped for re-run on Wave 3C real data (SHAPE-IM(3)).
"""

from __future__ import annotations

from backend.training.degenerate import NormMode, channel_statistics, derive_threshold
from backend.training.degenerate.constants import MIN_CHANNELS_FOR_DERIVATION
from contracts.recorder import OBSERVATION_STATE_KEY
from tests.wp4a03.fixtures import clean_stats, fault_stationary_vel


def test_separated_distribution_yields_threshold_between_the_clusters() -> None:
    # One collapsed channel (statistic ~0) among many healthy (statistic ~1) is a
    # clearly bimodal distribution; the threshold lands strictly between the clusters.
    case = fault_stationary_vel()
    channel_stats = case.stats[OBSERVATION_STATE_KEY]
    statistics = [
        v for _, v in channel_statistics(case.config.names, channel_stats, NormMode.MEAN_STD)
    ]

    derivation = derive_threshold(NormMode.MEAN_STD, statistics)

    assert derivation.separated
    assert derivation.threshold is not None
    # Between the degenerate cluster (0) and the healthy cluster (1.0).
    assert 0.0 < derivation.threshold < 1.0
    assert "valley" in derivation.rationale
    assert derivation.needs_real_data_rerun is True


def test_unimodal_distribution_declines_and_defers_to_show_all() -> None:
    # Every channel healthy: no valley, so the harness abandons the auto-threshold
    # rather than inventing one, and the rationale says so (02c §1.3 step 4).
    config, stats = clean_stats()
    statistics = [
        v
        for _, v in channel_statistics(
            config.names, stats[OBSERVATION_STATE_KEY], NormMode.MEAN_STD
        )
    ]

    derivation = derive_threshold(NormMode.MEAN_STD, statistics)

    assert derivation.separated is False
    assert derivation.threshold is None
    assert "abandon auto-threshold" in derivation.rationale


def test_too_few_channels_declines_rather_than_guessing() -> None:
    derivation = derive_threshold(NormMode.MEAN_STD, [0.0] * (MIN_CHANNELS_FOR_DERIVATION - 1))
    assert derivation.separated is False
    assert derivation.threshold is None


def test_histogram_is_populated_for_a_real_distribution() -> None:
    case = fault_stationary_vel()
    statistics = [
        v
        for _, v in channel_statistics(
            case.config.names, case.stats[OBSERVATION_STATE_KEY], NormMode.MEAN_STD
        )
    ]
    derivation = derive_threshold(NormMode.MEAN_STD, statistics)
    # The channel-std histogram is real evidence, not empty.
    assert sum(derivation.histogram_counts) == len(statistics)
    assert len(derivation.histogram_edges) == len(derivation.histogram_counts) + 1


def test_show_all_fallback_lists_every_channel() -> None:
    # When the harness declines, the show-all display carries one entry per channel.
    config, stats = clean_stats()
    table = channel_statistics(config.names, stats[OBSERVATION_STATE_KEY], NormMode.MEAN_STD)
    assert len(table) == len(config.names)
    assert {name for name, _ in table} == set(config.names)
