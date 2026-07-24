"""WP-3D-03 — exact-quantile vs histogram-approximate deviation report.

`02b` §8.1 WP-3D-03: `compute_stats` estimates quantiles from a histogram (then
count-weight-averages them across episodes), so the approximation error against the
exact `numpy.quantile` must be measured, not assumed. The report covers every channel
at every level; the error is small on a well-behaved channel and, as the report shows,
can be large on a near-degenerate one — which is exactly why measuring it is required.
"""

from __future__ import annotations

import backend.dataset.stats as stats
from contracts.recorder import ACTION_KEY, OBSERVATION_STATE_KEY
from tests.wp3d03 import support


def test_report_covers_every_channel_and_level() -> None:
    """A deviation is reported for each channel at each of the five levels."""
    feats = support.features()
    episodes = [support.episode(index, frames=20) for index in range(4)]
    result = stats.fit_normalization_stats(iter(episodes), feats)
    values = support.concat_values(episodes)

    report = stats.quantile_deviation_report(result.per_feature, values)

    action_channels = values[ACTION_KEY].shape[1]
    state_channels = values[OBSERVATION_STATE_KEY].shape[1]
    expected = (action_channels + state_channels) * len(stats.QUANTILE_LEVELS)
    assert len(report.deviations) == expected


def test_report_quantifies_a_finite_deviation() -> None:
    """The deviation is finite and well-formed for every channel and level."""
    import numpy as np

    feats = support.features()
    episodes = [support.episode(index, frames=20) for index in range(4)]
    result = stats.fit_normalization_stats(iter(episodes), feats)
    values = support.concat_values(episodes)

    report = stats.quantile_deviation_report(result.per_feature, values)

    assert np.isfinite(report.max_abs_deviation)
    assert report.max_abs_deviation >= 0.0
    for deviation in report.deviations:
        assert np.isfinite(deviation.exact)
        assert np.isfinite(deviation.approx)
        assert deviation.abs_deviation == abs(deviation.exact - deviation.approx)
    assert report.max_abs_deviation == max(
        deviation.abs_deviation for deviation in report.deviations
    )


def test_exact_quantiles_match_numpy_on_a_single_episode() -> None:
    """The exact-quantile helper is `numpy.quantile`, so it matches it exactly."""
    import numpy as np

    feats = support.features()
    episode = support.episode(0, frames=30)
    result = stats.fit_normalization_stats([episode], feats)
    values = {ACTION_KEY: episode[ACTION_KEY]}

    exact = stats.exact_quantiles(values[ACTION_KEY])
    for key, level in zip(stats.QUANTILE_KEYS, stats.QUANTILE_LEVELS, strict=True):
        assert np.allclose(exact[key], np.quantile(episode[ACTION_KEY], level, axis=0))

    # The report simply differences these against the fitted (approximate) table.
    report = stats.quantile_deviation_report(result.per_feature, values)
    assert report.deviations
