"""Shared builders for the WP-4A-04 normalization-contract tests.

The synthetic 48-dim dataset (`contracts.fixtures.synthetic_dataset`) stands in for a
real recording; these helpers turn it into the `compute_episode_stats` inputs the
committed fit consumes, and assemble a train/val/test split map for the pipeline. The
statistics themselves come from the committed WP-3D-03 fit — this band tests the
contract built on top of them, not the fit.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

import backend.dataset.stats as stats
from backend.dataset.stats.episodes import numeric_episode_data, numeric_features
from contracts.fixtures.synthetic_dataset import build_synthetic_dataset
from contracts.recorder import ACTION_KEY, OBSERVATION_STATE_KEY

DEFAULT_FRAMES = 12


def features() -> dict[str, dict[str, object]]:
    """The numeric `action`/`observation.state` feature description for the fixture."""
    return numeric_features(build_synthetic_dataset(0, DEFAULT_FRAMES).config)


def episode(index: int, frames: int = DEFAULT_FRAMES) -> dict[str, np.ndarray]:
    """One synthetic episode's numeric `compute_episode_stats` input."""
    return numeric_episode_data(build_synthetic_dataset(index, frames))


def fit(count: int = 3) -> stats.NormalizationStats:
    """Fit a small deterministic train normalization from `count` synthetic episodes."""
    return stats.fit_normalization_stats([episode(index) for index in range(count)], features())


def split_episodes() -> dict[str, list[dict[str, np.ndarray]]]:
    """A train/val/test split map of disjoint synthetic episodes for the pipeline."""
    return {
        "train": [episode(index) for index in range(3)],
        "val": [episode(index) for index in range(3, 5)],
        "test": [episode(index) for index in range(5, 7)],
    }


def concat_values(episodes: Sequence[dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    """Concatenate episodes' per-feature frames, for the exact-quantile report."""
    return {
        ACTION_KEY: np.concatenate([e[ACTION_KEY] for e in episodes], axis=0),
        OBSERVATION_STATE_KEY: np.concatenate([e[OBSERVATION_STATE_KEY] for e in episodes], axis=0),
    }
