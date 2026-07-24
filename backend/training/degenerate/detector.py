"""The per-normalization-mode degenerate-channel detector (`02c` §1.3, `FR-TRN-067`).

A degenerate channel is one whose per-channel statistic has collapsed to ~0: a
STATIONARY joint's `.vel` is a constant 0, a NON-CONTACT span's `.torque` is
near-constant. LeRobot's normalizer then divides by `denom = statistic + eps`
(eps=1e-8, floored — N-1 ledger resolution), so the channel's residual noise is
amplified ~1e6 and dominates the loss with no exception raised (`02c` §1.3 physics
block). This module DETECTS that channel; it cannot fix it — element-wise
normalization is LeRobot's contract and `FR-TRN-069` forbids the per-group
rescaling that could otherwise rescue the channel, so channel EXCLUDE is the only
remedy and that limit is structural, stated here rather than papered over.

Two disciplines this module holds:

- one statistic per mode, never one formula (`02c` §1.3 ③): MEAN_STD reads `std`,
  MIN_MAX reads `max−min`, QUANTILES reads `q99−q01`, each by its own metric key;
- location by NAME, never by index (`FR-TRN-063` trap): the metric arrays are
  positionally aligned with `names` by contract, but the joint/component a finding
  reports is parsed from the name string, so a rotated names order still names the
  same logical channel rather than mislabelling position 5 as a fixed motor.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from backend.training.degenerate.constants import (
    LEROBOT_NORMALIZE_EPS,
    MAX_KEY,
    MIN_KEY,
    Q01_KEY,
    Q99_KEY,
    STD_KEY,
)
from backend.training.degenerate.finding import DegenerateFinding, NormMode
from backend.training.preflight import ObservationConfig, split_channel
from contracts.recorder import OBSERVATION_STATE_KEY

# The per-channel metric-array map for one feature: metric key -> value per channel.
# This is the shape one `meta/stats.json` feature entry carries (e.g.
# `stats["observation.state"]["std"]` is one float per state channel).
ChannelStats = Mapping[str, Sequence[float]]


def _metric(channel_stats: ChannelStats, metric: str, index: int, channel_name: str) -> float:
    """Read one metric value for one channel, or raise a locating error.

    Args:
        channel_stats: The feature's metric-array map.
        metric: The metric key.
        index: The channel index into the metric array.
        channel_name: The channel name, for the error message only.

    Returns:
        (float) The metric value for the channel.

    Raises:
        KeyError: When the metric is absent — a stats file missing the key a mode
            needs is a defect the detector must surface, not read as "not degenerate".
        IndexError: When the metric array is shorter than `names` — a stats/names
            misalignment that would otherwise corrupt every reading past it.
    """
    array = channel_stats.get(metric)
    if array is None:
        raise KeyError(
            f"stats for channel {channel_name!r} is missing metric {metric!r}; "
            "the degenerate detector cannot judge a mode whose statistic is absent"
        )
    return float(array[index])


def channel_statistic(
    channel_stats: ChannelStats, norm_mode: NormMode, index: int, channel_name: str
) -> float:
    """Return the degeneracy statistic for one channel under one mode.

    Each mode is judged by its own statistic (`FR-TRN-067`, `02c` §1.3 ③), never a
    single shared formula:

    - MEAN_STD -> `std`;
    - MIN_MAX -> `max − min`;
    - QUANTILES -> `q99 − q01`.

    Args:
        channel_stats: The feature's metric-array map.
        norm_mode: The normalization mode to judge under.
        index: The channel index.
        channel_name: The channel name, for error location.

    Returns:
        (float) The mode's statistic for the channel.
    """
    if norm_mode is NormMode.MEAN_STD:
        return _metric(channel_stats, STD_KEY, index, channel_name)
    if norm_mode is NormMode.MIN_MAX:
        span_max = _metric(channel_stats, MAX_KEY, index, channel_name)
        span_min = _metric(channel_stats, MIN_KEY, index, channel_name)
        return span_max - span_min
    high = _metric(channel_stats, Q99_KEY, index, channel_name)
    low = _metric(channel_stats, Q01_KEY, index, channel_name)
    return high - low


def amplification_estimate(statistic: float) -> float:
    """Estimate the normalizer's gain for a channel of this statistic.

    The gain is 1/(statistic + eps): the factor by which a raw deviation in the
    channel is scaled before it enters the loss. A well-conditioned channel
    (statistic O(1)) has gain O(1); a degenerate channel (statistic -> 0) has gain
    -> 1/eps = 1e8, the mechanism by which a zero-information channel dominates
    (`02c` §1.3 physics block). An estimate — the actual loss contribution also
    depends on the channel's residual, which the stats do not carry.

    Args:
        statistic: The channel's per-mode statistic.

    Returns:
        (float) The estimated normalizer gain.
    """
    return 1.0 / (abs(statistic) + LEROBOT_NORMALIZE_EPS)


def detect_degenerate_channels(
    names: Sequence[str],
    channel_stats: ChannelStats,
    norm_mode: NormMode,
    threshold: float,
) -> tuple[DegenerateFinding, ...]:
    """Flag every channel whose per-mode statistic falls below the threshold.

    The metric arrays in `channel_stats` are positionally aligned with `names` by
    the `CTR-REC@v1` contract, so index `i` reads channel `names[i]`. The finding it
    yields, however, is located by the NAME (`split_channel`), not by the index, so
    a names/stats order that has been rotated together still names the same logical
    channel (`FR-TRN-063` discipline).

    Args:
        names: The `observation.state` channel names, in stats-array order.
        channel_stats: The feature's metric-array map.
        norm_mode: The mode whose statistic decides degeneracy.
        threshold: The σ_min/δ_min to compare against — supplied by the derivation
            harness, never a hard-coded plan value (`02c` §1.3 σ_min block).

    Returns:
        (tuple[DegenerateFinding, ...]) One finding per degenerate channel, in name
            order, each naming its joint and component.
    """
    findings: list[DegenerateFinding] = []
    for index, name in enumerate(names):
        statistic = channel_statistic(channel_stats, norm_mode, index, name)
        if statistic < threshold:
            joint, component = split_channel(name)
            findings.append(
                DegenerateFinding(
                    channel_name=name,
                    joint=joint,
                    component=component,
                    norm_mode=norm_mode,
                    statistic=statistic,
                    threshold=threshold,
                    amplification_estimate=amplification_estimate(statistic),
                )
            )
    return tuple(findings)


def channel_statistics(
    names: Sequence[str], channel_stats: ChannelStats, norm_mode: NormMode
) -> tuple[tuple[str, float], ...]:
    """Return every channel's per-mode statistic, for the show-all fallback.

    When the derivation harness cannot separate a degenerate cluster from a normal
    one it abandons the auto-threshold and every channel's statistic is shown for a
    human to pick (`02c` §1.3 σ_min block step 4). This is that display: no verdict,
    just the number per channel.

    Args:
        names: The channel names in stats-array order.
        channel_stats: The feature's metric-array map.
        norm_mode: The mode whose statistic to report.

    Returns:
        (tuple[tuple[str, float], ...]) `(channel_name, statistic)` per channel.
    """
    return tuple(
        (name, channel_statistic(channel_stats, norm_mode, index, name))
        for index, name in enumerate(names)
    )


def detect_in_observation_state(
    config: ObservationConfig,
    stats: Mapping[str, ChannelStats],
    norm_mode: NormMode,
    threshold: float,
) -> tuple[DegenerateFinding, ...]:
    """Run the detector over `observation.state`, addressing channels by config names.

    `config.names` is the canonical channel order (`FR-TRN-061`); the stats map is
    keyed by feature, so the state feature's metric arrays are read and aligned to
    those names. Consuming the committed WP-4A-02 `ObservationConfig` keeps the
    channel authority the trainer's, not a second list.

    Args:
        config: The observation configuration derived by WP-4A-02 preflight.
        stats: The `meta/stats.json` map, feature key -> metric-array map.
        norm_mode: The normalization mode to judge under.
        threshold: The derived σ_min/δ_min.

    Returns:
        (tuple[DegenerateFinding, ...]) Degenerate findings over the state channels.
    """
    channel_stats = stats.get(OBSERVATION_STATE_KEY, {})
    return detect_degenerate_channels(config.names, channel_stats, norm_mode, threshold)
