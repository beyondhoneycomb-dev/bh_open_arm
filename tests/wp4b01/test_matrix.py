"""WP-4B-01 three-axis matrix: the six CG-4B-01 blocking gates.

The engine's job is to BLOCK (`10` FR-TRN-064 negative branch): these prove the
blocks fire with their source, that the observation-config axis auto-removes the
32-capped families with no manual refresh, that the projection axis brings them
back, and that each FR-TRN-017 rule blocks on its own.
"""

from __future__ import annotations

import dataclasses

from backend.compat.policy_matrix import CompatibilityMatrix, TrainingRequest, build_matrix
from backend.training.preflight import derive_observation_config
from backend.training.projection import ProjectionKind
from contracts.fixtures.synthetic_dataset import build_synthetic_dataset
from tests.wp4b01.fixtures import bimanual_full, single_arm_full

_CAPPED_FAMILIES = ("smolvla", "pi0", "pi05")


def _matrix() -> CompatibilityMatrix:
    return build_matrix()


def _valid_request() -> TrainingRequest:
    """A request that trips no structural rule, for injecting exactly one at a time."""
    return TrainingRequest(
        n_obs_steps=1,
        n_action_steps=1,
        chunk_size=100,
        temporal_ensemble=False,
        n_cameras=1,
        has_state=True,
    )


def test_fixture_matches_committed_observation_config() -> None:
    """The 48-dim fixture equals the WP-4A-02 config derived from the real dataset."""
    derived = derive_observation_config(build_synthetic_dataset().info_features)
    fixture = bimanual_full()
    assert fixture.names == derived.names
    assert fixture.state_dim == derived.state_dim == 48


def test_cg_4b_01a_bimanual48_blocks_smolvla_with_source() -> None:
    """CG-4B-01a: bimanual 48 x SmolVLA is blocked, reason names 32 and the source."""
    verdict = _matrix().evaluate("smolvla", bimanual_full(), ProjectionKind.FULL)
    assert verdict.allowed is False
    reason = next(r for r in verdict.blocking_reasons if r.field_name == "max_state_dim")
    assert reason.observed == 48
    assert reason.limit == 32
    assert reason.rule_id == "FR-TRN-017f"
    assert reason.source.endswith("configuration_smolvla.py")
    assert "max_state_dim" in reason.message


def test_cg_4b_01b_pi_families_block_but_groot_allows() -> None:
    """CG-4B-01b: pi0/pi05 blocked on 48; GR00T (132) allowed."""
    matrix = _matrix()
    config = bimanual_full()
    for policy_id in ("pi0", "pi05"):
        verdict = matrix.evaluate(policy_id, config, ProjectionKind.FULL)
        assert verdict.allowed is False
        assert any(r.limit == 32 for r in verdict.blocking_reasons)
    groot = matrix.evaluate("groot", config, ProjectionKind.FULL)
    assert groot.allowed is True
    assert groot.blocking_reasons == ()


def test_cg_4b_01c_switching_obs_config_auto_removes_capped_families() -> None:
    """CG-4B-01c: 24->48 drops SmolVLA/pi0/pi05 from usable with no manual edit."""
    matrix = _matrix()
    usable_24 = matrix.usable_policies(single_arm_full(), ProjectionKind.FULL)
    usable_48 = matrix.usable_policies(bimanual_full(), ProjectionKind.FULL)
    for policy_id in _CAPPED_FAMILIES:
        assert policy_id in usable_24
        assert policy_id not in usable_48


def test_cg_4b_01d_pos_only_projection_brings_capped_families_back() -> None:
    """CG-4B-01d: projecting 48 to .pos-only (16) re-admits the 32-capped families."""
    matrix = _matrix()
    config = bimanual_full()
    usable_full = matrix.usable_policies(config, ProjectionKind.FULL)
    usable_pos = matrix.usable_policies(config, ProjectionKind.POS_ONLY)
    for policy_id in _CAPPED_FAMILIES:
        assert policy_id not in usable_full
        assert policy_id in usable_pos


def test_cg_4b_01d_projection_is_a_real_third_axis() -> None:
    """The only change between the two verdicts is the projection, proving axis 3."""
    matrix = _matrix()
    config = bimanual_full()
    blocked = matrix.evaluate("smolvla", config, ProjectionKind.FULL)
    allowed = matrix.evaluate("smolvla", config, ProjectionKind.POS_ONLY)
    assert blocked.allowed is False
    assert allowed.allowed is True


def test_cg_4b_01e_each_structural_rule_blocks_independently() -> None:
    """CG-4B-01e: injecting one FR-TRN-017 violation surfaces exactly that rule."""
    matrix = _matrix()
    small = single_arm_full()  # 24-dim, under every cap, so no dimension block interferes
    big = bimanual_full()
    base = _valid_request()
    cases = [
        ("act", small, dataclasses.replace(base, n_obs_steps=2), "FR-TRN-017a"),
        (
            "act",
            small,
            dataclasses.replace(base, n_action_steps=200, chunk_size=100),
            "FR-TRN-017b",
        ),
        (
            "act",
            small,
            dataclasses.replace(base, temporal_ensemble=True, n_action_steps=2, chunk_size=100),
            "FR-TRN-017c",
        ),
        ("diffusion", small, dataclasses.replace(base, has_state=False), "FR-TRN-017d"),
        ("vqbet", small, dataclasses.replace(base, n_cameras=2), "FR-TRN-017e"),
        ("smolvla", big, base, "FR-TRN-017f"),
    ]
    for policy_id, config, request, expected in cases:
        verdict = matrix.evaluate(policy_id, config, ProjectionKind.FULL, request)
        rule_ids = [reason.rule_id for reason in verdict.blocking_reasons]
        assert rule_ids == [expected], f"{policy_id}: expected [{expected}], got {rule_ids}"


def test_blocked_verdict_is_a_hard_stop_not_a_warning() -> None:
    """A blocked cell is `allowed=False` with reasons — never allowed-with-warning."""
    verdict = _matrix().evaluate("smolvla", bimanual_full(), ProjectionKind.FULL)
    assert verdict.allowed is False
    assert len(verdict.blocking_reasons) >= 1


def test_unknown_policy_is_a_key_error_not_silent_pass() -> None:
    """An unregistered family is a defect, not a silently uncapped policy."""
    matrix = _matrix()
    config = bimanual_full()
    try:
        matrix.evaluate("not_a_policy", config, ProjectionKind.FULL)
    except KeyError:
        return
    raise AssertionError("evaluate() accepted an unknown policy without raising")
