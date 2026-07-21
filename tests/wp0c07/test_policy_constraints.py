"""Acceptance ④ — the six FR-TRN-017 conditions, each blocked under its own code.

④ requires each of the six structural conditions to be detected as a *distinct*
block, never merged into one generic "config invalid". This suite fires one
fixture per condition, asserts the returned code is exactly that condition's code,
and asserts the six codes are mutually distinct. It also checks the non-violating
cases pass, so the validator is not blocking by refusing everything.
"""

from __future__ import annotations

import pytest

from backend.learning.policy_constraints import (
    DatasetProfile,
    PolicyConstraintCode,
    PolicySpec,
    PolicyStructuralValidator,
)

BIMANUAL_48 = DatasetProfile(state_dim=48, action_dim=16, n_cameras=1, has_state=True)


def _codes(policy: PolicySpec, dataset: DatasetProfile) -> list[PolicyConstraintCode]:
    """Return the violation codes for one policy/dataset pair."""
    return [violation.code for violation in PolicyStructuralValidator().validate(policy, dataset)]


def test_act_multiple_obs_steps_blocked() -> None:
    """Condition 1: ACT n_obs_steps != 1."""
    policy = PolicySpec("act", n_obs_steps=2, n_action_steps=50, chunk_size=100)
    assert _codes(policy, BIMANUAL_48) == [PolicyConstraintCode.ACT_MULTIPLE_OBS_STEPS]


def test_act_action_steps_exceed_chunk_blocked() -> None:
    """Condition 2: ACT n_action_steps > chunk_size."""
    policy = PolicySpec("act", n_obs_steps=1, n_action_steps=120, chunk_size=100)
    assert _codes(policy, BIMANUAL_48) == [PolicyConstraintCode.ACT_ACTION_STEPS_EXCEED_CHUNK]


def test_temporal_ensemble_action_steps_blocked() -> None:
    """Condition 3: temporal ensembling with n_action_steps != 1."""
    policy = PolicySpec(
        "act", n_obs_steps=1, n_action_steps=10, chunk_size=100, temporal_ensemble=True
    )
    assert _codes(policy, BIMANUAL_48) == [PolicyConstraintCode.TEMPORAL_ENSEMBLE_ACTION_STEPS]


def test_diffusion_missing_state_blocked() -> None:
    """Condition 4: Diffusion with no observation.state."""
    policy = PolicySpec("diffusion")
    dataset = DatasetProfile(state_dim=None, action_dim=16, n_cameras=1, has_state=False)
    assert _codes(policy, dataset) == [PolicyConstraintCode.DIFFUSION_MISSING_STATE]


def test_vqbet_multiple_cameras_blocked() -> None:
    """Condition 5: VQ-BeT with two or more cameras."""
    policy = PolicySpec("vqbet")
    dataset = DatasetProfile(state_dim=48, action_dim=16, n_cameras=2, has_state=True)
    assert _codes(policy, dataset) == [PolicyConstraintCode.VQBET_MULTIPLE_CAMERAS]


def test_dimension_cap_exceeded_blocked() -> None:
    """Condition 6: a dimension-capped policy over its cap (FR-TRN-064)."""
    for capped in ("smolvla", "pi0", "pi05"):
        assert _codes(PolicySpec(capped), BIMANUAL_48) == [
            PolicyConstraintCode.DIMENSION_CAP_EXCEEDED
        ]


def test_the_six_codes_are_distinct() -> None:
    """④ the six conditions map to six mutually distinct codes."""
    fixtures = [
        (PolicySpec("act", n_obs_steps=2), BIMANUAL_48),
        (PolicySpec("act", n_action_steps=120, chunk_size=100), BIMANUAL_48),
        (PolicySpec("act", n_action_steps=10, temporal_ensemble=True), BIMANUAL_48),
        (PolicySpec("diffusion"), DatasetProfile(None, 16, 1, has_state=False)),
        (PolicySpec("vqbet"), DatasetProfile(48, 16, 2, has_state=True)),
        (PolicySpec("smolvla"), BIMANUAL_48),
    ]
    seen = [_codes(policy, dataset)[0] for policy, dataset in fixtures]
    assert len(set(seen)) == 6
    assert set(seen) == set(PolicyConstraintCode)


def test_valid_configs_are_not_over_blocked() -> None:
    """A well-formed pair for each policy passes without any violation."""
    single_arm_24 = DatasetProfile(state_dim=24, action_dim=8, n_cameras=1, has_state=True)
    assert (
        _codes(PolicySpec("act", n_obs_steps=1, n_action_steps=50, chunk_size=100), BIMANUAL_48)
        == []
    )
    assert _codes(PolicySpec("diffusion"), BIMANUAL_48) == []
    assert _codes(PolicySpec("vqbet"), single_arm_24) == []
    # Single-arm 24 is within the 32 cap, so a capped policy accepts it (no over-block).
    assert _codes(PolicySpec("smolvla"), single_arm_24) == []


def test_multiple_violations_are_reported_separately() -> None:
    """Two simultaneous ACT violations are two distinct codes, never merged."""
    policy = PolicySpec("act", n_obs_steps=2, n_action_steps=120, chunk_size=100)
    codes = set(_codes(policy, BIMANUAL_48))
    assert PolicyConstraintCode.ACT_MULTIPLE_OBS_STEPS in codes
    assert PolicyConstraintCode.ACT_ACTION_STEPS_EXCEED_CHUNK in codes


def test_dimension_cap_matches_real_lerobot_default() -> None:
    """The 32 cap is the value the pinned SmolVLA/pi0 configs actually declare."""
    from lerobot.policies.pi0.configuration_pi0 import PI0Config
    from lerobot.policies.smolvla.configuration_smolvla import SmolVLAConfig

    assert SmolVLAConfig().max_state_dim == 32
    assert PI0Config().max_state_dim == 32
    # 48 exceeds it; the validator agrees with the config's own constant.
    assert _codes(PolicySpec("smolvla"), BIMANUAL_48) == [
        PolicyConstraintCode.DIMENSION_CAP_EXCEEDED
    ]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
