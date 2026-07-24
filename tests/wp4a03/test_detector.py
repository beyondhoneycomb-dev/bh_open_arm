"""CG-4A-03a/b/c — the degenerate detector fires per mode, located by name.

Every detection gate is proved with a fixture that collapses one channel and MUST
make the detector fire on exactly that channel, located by joint and component
(`02c` §1.3 ①/②). The threshold is not hard-coded: it is DERIVED by the harness from
the fixture's own channel-statistic distribution, so these tests exercise the whole
pipeline (harness -> detector), not the detector against a magic number.
"""

from __future__ import annotations

from backend.training.degenerate import (
    NormMode,
    channel_statistic,
    channel_statistics,
    derive_threshold,
    detect_degenerate_channels,
    detect_in_observation_state,
)
from backend.training.degenerate.detector import ChannelStats
from backend.training.preflight import Component
from contracts.recorder import OBSERVATION_STATE_KEY, VELOCITY_SUFFIX
from tests.wp4a03.fixtures import (
    clean_stats,
    fault_noncontact_torque,
    fault_stationary_vel,
    per_mode_divergent_channel,
)


def _derived_threshold(
    config_names: tuple[str, ...], channel_stats: ChannelStats, norm_mode: NormMode
) -> float:
    statistics = [value for _, value in channel_statistics(config_names, channel_stats, norm_mode)]
    derivation = derive_threshold(norm_mode, statistics)
    assert derivation.separated, f"{norm_mode}: harness must separate a lone degenerate channel"
    assert derivation.threshold is not None
    return derivation.threshold


def test_cg_4a_03a_stationary_vel_detected_with_joint_and_component() -> None:
    case = fault_stationary_vel()
    channel_stats = case.stats[OBSERVATION_STATE_KEY]
    threshold = _derived_threshold(case.config.names, channel_stats, NormMode.MEAN_STD)

    findings = detect_in_observation_state(case.config, case.stats, NormMode.MEAN_STD, threshold)

    assert len(findings) == 1, "exactly the one collapsed channel is degenerate"
    finding = findings[0]
    assert finding.channel_name == case.target_channel
    # Located by name: the joint is the target's motor key and the component is .vel.
    assert case.target_channel.startswith(finding.joint)
    assert finding.component is Component.VEL
    assert finding.norm_mode is NormMode.MEAN_STD
    assert finding.statistic == 0.0


def test_cg_4a_03b_noncontact_torque_detected_with_joint_and_component() -> None:
    case = fault_noncontact_torque()
    channel_stats = case.stats[OBSERVATION_STATE_KEY]
    threshold = _derived_threshold(case.config.names, channel_stats, NormMode.MEAN_STD)

    findings = detect_in_observation_state(case.config, case.stats, NormMode.MEAN_STD, threshold)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.channel_name == case.target_channel
    assert finding.component is Component.TORQUE
    # The near-constant residual is decades below the threshold, so it is caught.
    assert finding.statistic < threshold


def test_cg_4a_03b_amplification_estimate_is_large_for_a_degenerate_channel() -> None:
    # The physics the WP exists to expose: a collapsed channel's normalizer gain is
    # enormous (~1e6+), the mechanism by which it dominates the loss.
    case = fault_stationary_vel()
    channel_stats = case.stats[OBSERVATION_STATE_KEY]
    threshold = _derived_threshold(case.config.names, channel_stats, NormMode.MEAN_STD)
    finding = detect_in_observation_state(case.config, case.stats, NormMode.MEAN_STD, threshold)[0]
    assert finding.amplification_estimate > 1e6


def test_cg_4a_03c_each_mode_is_judged_by_its_own_statistic() -> None:
    # One channel where std=0 but max-min=5.0 and q99-q01=4.0: a detector that read
    # the wrong metric for a mode would give the wrong number and the wrong verdict.
    names, channel_stats = per_mode_divergent_channel()
    threshold = 1e-3

    mean_std = channel_statistic(channel_stats, NormMode.MEAN_STD, 0, names[0])
    min_max = channel_statistic(channel_stats, NormMode.MIN_MAX, 0, names[0])
    quantiles = channel_statistic(channel_stats, NormMode.QUANTILES, 0, names[0])

    # Each mode reads a DIFFERENT statistic — not one shared formula (02c §1.3 ③).
    assert mean_std == 0.0
    assert min_max == 5.0
    assert quantiles == 4.0
    assert len({mean_std, min_max, quantiles}) == 3

    # And the verdict follows the mode's own statistic: only MEAN_STD is degenerate
    # here; the same channel is NOT degenerate under MIN_MAX or QUANTILES.
    assert detect_degenerate_channels(names, channel_stats, NormMode.MEAN_STD, threshold)
    assert not detect_degenerate_channels(names, channel_stats, NormMode.MIN_MAX, threshold)
    assert not detect_degenerate_channels(names, channel_stats, NormMode.QUANTILES, threshold)


def test_cg_4a_03c_all_three_modes_fire_on_a_constant_zero_channel() -> None:
    # A constant-0 channel is degenerate under every mode (std, extent, and span all
    # collapse), and each fires by its own statistic.
    case = fault_stationary_vel()
    channel_stats = case.stats[OBSERVATION_STATE_KEY]
    for norm_mode in NormMode:
        threshold = _derived_threshold(case.config.names, channel_stats, norm_mode)
        findings = detect_in_observation_state(case.config, case.stats, norm_mode, threshold)
        assert len(findings) == 1, norm_mode
        assert findings[0].channel_name == case.target_channel
        assert findings[0].norm_mode is norm_mode


def test_detection_is_by_name_not_by_index_under_rotation() -> None:
    # The FR-TRN-063 discipline: metric arrays are positionally aligned with names,
    # but a finding is located by the NAME. Rotate the (name, stat) pairs together;
    # the collapsed channel moves position but keeps its name, and the detector must
    # still report that same channel — never "position N is always motor X".
    case = fault_stationary_vel()
    channel_stats = case.stats[OBSERVATION_STATE_KEY]
    names = case.config.names
    threshold = _derived_threshold(names, channel_stats, NormMode.MEAN_STD)

    shift = 5
    rotated_names = names[shift:] + names[:shift]
    rotated_stats = {
        metric: list(array[shift:]) + list(array[:shift]) for metric, array in channel_stats.items()
    }

    original = detect_degenerate_channels(names, channel_stats, NormMode.MEAN_STD, threshold)[0]
    after = detect_degenerate_channels(rotated_names, rotated_stats, NormMode.MEAN_STD, threshold)[
        0
    ]

    assert after.channel_name == original.channel_name == case.target_channel
    assert after.joint == original.joint
    assert after.component == original.component


def test_clean_stats_produce_no_findings() -> None:
    # The negative control: every channel healthy, so no channel is degenerate at a
    # threshold any real degenerate channel would fall below.
    config, stats = clean_stats()
    findings = detect_in_observation_state(config, stats, NormMode.MEAN_STD, 1e-3)
    assert findings == ()


def test_target_channel_is_really_a_velocity_channel() -> None:
    # Guards the fixture: the stationary-vel case really targets a `.vel` channel, so
    # the `.vel` degeneracy path is exercised rather than bypassed.
    case = fault_stationary_vel()
    assert case.target_channel.endswith(VELOCITY_SUFFIX)
