"""Acceptance ①②⑤ — the synthetic dataset is a real LeRobot v3.0 recording.

① a synthetic 48-dim dataset loads under the LeRobot v3.0 schema; ② with
``use_velocity_and_torque=True`` the bimanual ``observation.state`` is 48 and the
``action`` is position-only 16 (`10` FR-TRN-074); ⑤ ``timestamp`` is excluded from
the policy features, verified against the real ``dataset_to_policy_features`` — not
asserted from a copy of the rule.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.learning.synthetic_dataset import (
    SyntheticDatasetSpec,
    build_synthetic_dataset,
    state_action_feature_spec,
)


def _load(root: Path, repo_id: str):
    """Load a written dataset back through the real LeRobot loader."""
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    return LeRobotDataset(repo_id=repo_id, root=root)


def test_dataset_loads_under_v30_schema(tmp_path: Path) -> None:
    """① the generated dataset loads and reports codebase version v3.0."""
    from lerobot.datasets.dataset_metadata import CODEBASE_VERSION

    spec = SyntheticDatasetSpec()
    result = build_synthetic_dataset(spec, tmp_path / "ds")

    # A load that raises no version-incompatibility error is itself the v3.0
    # acceptance: the loader checks the stored codebase_version against
    # CODEBASE_VERSION. The explicit assertions pin the version fact as well.
    assert CODEBASE_VERSION == "v3.0"
    loaded = _load(result.root, spec.repo_id)
    assert loaded.meta.info.codebase_version == "v3.0"
    assert loaded.num_frames == result.num_frames
    assert loaded.num_episodes == result.num_episodes


def test_velocity_torque_state_is_48_action_is_16(tmp_path: Path) -> None:
    """② bimanual + use_velocity_and_torque=True -> state 48, action position-only 16."""
    spec = SyntheticDatasetSpec(bimanual=True, use_velocity_and_torque=True)
    result = build_synthetic_dataset(spec, tmp_path / "ds")

    assert result.state_dim == 48
    assert result.action_dim == 16

    loaded = _load(result.root, spec.repo_id)
    assert loaded.meta.features["observation.state"]["shape"] == (48,)
    assert loaded.meta.features["action"]["shape"] == (16,)

    # The action is position-only: every action channel name ends in `.pos`.
    action_names = loaded.meta.features["action"]["names"]
    assert len(action_names) == 16
    assert all(name.endswith(".pos") for name in action_names)


def test_action_is_position_only_even_without_velocity_torque(tmp_path: Path) -> None:
    """② the action stays position-only when the state drops velocity and torque."""
    spec = SyntheticDatasetSpec(bimanual=True, use_velocity_and_torque=False)
    features = state_action_feature_spec(spec)

    # State collapses to position-only 16; action is unchanged position-only 16.
    assert features["observation.state"]["shape"] == (16,)
    assert features["action"]["shape"] == (16,)
    assert all(name.endswith(".pos") for name in features["action"]["names"])


def test_timestamp_excluded_from_policy_features(tmp_path: Path) -> None:
    """⑤ timestamp is dropped by the real dataset_to_policy_features."""
    from lerobot.utils.feature_utils import dataset_to_policy_features

    spec = SyntheticDatasetSpec()
    result = build_synthetic_dataset(spec, tmp_path / "ds")
    loaded = _load(result.root, spec.repo_id)

    # timestamp is a real feature of the dataset (a DEFAULT_FEATURE)...
    assert "timestamp" in loaded.meta.features
    # ...and the real policy-feature builder structurally excludes it.
    policy_features = dataset_to_policy_features(loaded.meta.features)
    assert "timestamp" not in policy_features
    assert set(policy_features) == {"observation.state", "action"}
    assert policy_features["observation.state"].shape == (48,)
    assert policy_features["action"].shape == (16,)


def test_generator_is_deterministic(tmp_path: Path) -> None:
    """The synthetic draw is seeded, so two builds produce identical arrays."""
    from backend.learning.synthetic_dataset import generate_state_action_arrays

    spec = SyntheticDatasetSpec(seed=7)
    states_a, actions_a = generate_state_action_arrays(spec)
    states_b, actions_b = generate_state_action_arrays(spec)
    assert states_a.shape == (spec.episodes * spec.frames_per_episode, 48)
    assert actions_a.shape == (spec.episodes * spec.frames_per_episode, 16)
    assert (states_a == states_b).all()
    assert (actions_a == actions_b).all()


def test_features_reject_nothing_real_lerobot_accepts(tmp_path: Path) -> None:
    """The feature spec round-trips through LeRobot's own feature converter."""
    from lerobot.datasets.feature_utils import get_hf_features_from_features

    spec = SyntheticDatasetSpec()
    features = state_action_feature_spec(spec)
    hf = get_hf_features_from_features(features)
    assert "observation.state" in hf
    assert "action" in hf


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
