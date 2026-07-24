"""CG-4A-02a..e — the WP-4A-02 acceptance gates, each a MUST-BLOCK-on-fault (`02c` §1.2).

Every detection gate here is proved with a fault-injection fixture that must make
the checker fire; the one PASS gate is proved with the clean fixture and an EMPTY
findings set. The cross-verification (SHAPE-IM(2)) also shows each fault is
load-bearing: strip the fault and the same pair passes, so the fixture blocks
because of its injected defect and nothing else.
"""

from __future__ import annotations

from copy import deepcopy

from backend.training.preflight import (
    Component,
    PreflightCode,
    Verdict,
    derive_observation_config,
    preflight,
)
from contracts.recorder import TORQUE_SUFFIX
from tests.wp4a02.fixtures import (
    all_fault_cases,
    clean_pair,
    fault_quantiles_removed,
    fault_rename_rotation,
    fault_timestamp_promoted,
    fault_torque_stripped,
    smolvla_policy,
)


def test_cg_4a_02e_clean_fixture_passes_with_empty_findings() -> None:
    dataset, policy = clean_pair()
    report = preflight(dataset, policy)
    assert report.verdict is Verdict.PASS
    assert report.findings == ()


def test_cg_4a_02a_torque_stripped_blocks_without_misjudging_as_48() -> None:
    case = fault_torque_stripped()
    report = preflight(case.dataset, case.policy)
    assert report.verdict is Verdict.BLOCK
    assert case.expected_code in report.codes()

    # The config must be judged by names, not by the retained shape 48: with
    # `.torque` gone from names, this is a NON-vel/torque configuration, and the
    # 48 shape now disagrees with the shorter names.
    config = derive_observation_config(case.dataset.info_features)
    assert config.use_velocity_and_torque is False
    assert config.state_dim == len(config.names)
    assert config.state_dim != 48
    assert PreflightCode.OBSERVATION_STATE_SHAPE_MISMATCH in report.codes()


def test_cg_4a_02b_rename_rotation_blocks_and_names_the_channel() -> None:
    case = fault_rename_rotation()
    report = preflight(case.dataset, case.policy)
    assert report.verdict is Verdict.BLOCK
    order_findings = [f for f in report.findings if f.code is PreflightCode.OBSERVATION_STATE_ORDER]
    assert order_findings
    # The finding must locate the fault: a joint key and a per-motor component.
    finding = order_findings[0]
    assert finding.joint
    assert finding.component in set(Component)


def test_cg_4a_02c_missing_quantiles_with_pi05_blocks_and_suggests_augment() -> None:
    case = fault_quantiles_removed()
    report = preflight(case.dataset, case.policy)
    assert report.verdict is Verdict.BLOCK
    quantile_findings = [
        f for f in report.findings if f.code is PreflightCode.QUANTILE_STATS_MISSING
    ]
    assert quantile_findings
    assert {"observation.state", "action"} <= {f.channel_name for f in quantile_findings}
    # The augment script is SUGGESTED, never auto-run (auto-augment would silently
    # change the stats hash — 02c §0.4, §1.2 negative branch ③).
    for finding in quantile_findings:
        assert "augment_dataset_quantile_stats.py" in finding.detail
        assert "Not auto-run" in finding.detail


def test_cg_4a_02c_missing_quantiles_with_meanstd_policy_passes() -> None:
    # The negative control: the same stats deficit does not block a MEAN_STD policy,
    # proving the quantile gate keys on the policy's normalization mode, not on the
    # dataset or the policy's name.
    case = fault_quantiles_removed()
    report = preflight(case.dataset, smolvla_policy())
    assert report.verdict is Verdict.PASS


def test_cg_4a_02d_timestamp_promotion_blocks() -> None:
    case = fault_timestamp_promoted()
    report = preflight(case.dataset, case.policy)
    assert report.verdict is Verdict.BLOCK
    promotions = [f for f in report.findings if f.code is PreflightCode.STRUCTURAL_FEATURE_PROMOTED]
    assert promotions
    assert any(f.channel_name == "timestamp" for f in promotions)


def test_every_fault_case_blocks_with_its_expected_code() -> None:
    for case in all_fault_cases():
        report = preflight(case.dataset, case.policy)
        assert report.verdict is Verdict.BLOCK, case.gate_id
        assert case.expected_code in report.codes(), case.gate_id


def test_each_fault_is_load_bearing_clean_baseline_passes() -> None:
    # Cross-verification: the clean pair the faults are derived from passes, so each
    # fault fixture blocks because of its injected defect, not an incidental one.
    dataset, policy = clean_pair()
    assert preflight(dataset, policy).verdict is Verdict.PASS


def test_rename_rotation_only_blocks_because_of_the_rename() -> None:
    # The rotation fixture with its rename removed is the clean pair — it must pass,
    # isolating the rename as the sole cause of the block.
    case = fault_rename_rotation()
    without_rename = type(case.policy)(
        name=case.policy.name, normalization_modes=case.policy.normalization_modes
    )
    assert preflight(case.dataset, without_rename).verdict is Verdict.PASS


def test_preflight_does_not_mutate_the_dataset() -> None:
    # Preflight is read-only over the dataset: it suggests remediation, it never
    # rewrites stats or info (which would change the stats hash).
    case = fault_quantiles_removed()
    info_before = deepcopy(dict(case.dataset.info_features))
    stats_before = deepcopy(dict(case.dataset.stats))
    preflight(case.dataset, case.policy)
    assert dict(case.dataset.info_features) == info_before
    assert dict(case.dataset.stats) == stats_before


def test_preflight_is_deterministic() -> None:
    # A preflight verdict is a pure function of the pair — timing-independent and
    # repeatable, the same discipline the 4A band requires of its guards.
    case = fault_rename_rotation()
    first = preflight(case.dataset, case.policy)
    second = preflight(case.dataset, case.policy)
    assert first == second


def test_stripped_torque_names_have_no_torque_suffix() -> None:
    # Guards the fixture itself: the fault really removed every `.torque` channel,
    # so the checker's `.torque`-presence judgment is exercised, not bypassed.
    case = fault_torque_stripped()
    names = case.dataset.info_features["observation.state"]["names"]
    assert all(not str(name).endswith(TORQUE_SUFFIX) for name in names)
