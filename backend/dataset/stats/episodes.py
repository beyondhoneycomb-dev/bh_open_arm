"""Adapt a recorded episode into the `compute_stats` input shape (WP-3D-03).

LeRobot's `compute_episode_stats` consumes a `{feature_key: data}` mapping plus a
`features` description; numeric features are numpy arrays and image features are
lists of file paths. This module builds that mapping for the OpenArm feature set
from the synthetic dataset fixture (`contracts.fixtures.synthetic_dataset`, this
band's stand-in for a real recording — `02b` §5.2 WP-3A-06), deriving every
channel by name from `CTR-REC@v1` and reusing the recorder embed's feature-map
builder (`WP-3B-11`) rather than restating the dtype/shape/`names` bodies.
"""

from __future__ import annotations

import numpy as np

from backend.recorder.embed.dataset import create_features
from contracts.fixtures.synthetic_dataset import SyntheticDataset
from contracts.recorder import (
    ACTION_KEY,
    OBSERVATION_STATE_KEY,
    RecorderConfig,
    action_names,
    observation_state_names,
)

_FLOAT32 = np.float32


def numeric_features(config: RecorderConfig) -> dict[str, dict[str, object]]:
    """Return the `action`/`observation.state` feature description, from the recorder.

    Reuses `WP-3B-11`'s `create_features`, so the dtype, shape and `names` a
    consumer reads back are the recorder's own and cannot drift from `CTR-REC@v1`.

    Args:
        config: The recorder configuration the dataset was produced under.

    Returns:
        (dict) The `compute_stats` feature description for the two numeric features.
    """
    return create_features(config)


def numeric_episode_data(dataset: SyntheticDataset) -> dict[str, np.ndarray]:
    """Build the numeric `compute_episode_stats` input for one episode.

    Args:
        dataset: A validated synthetic episode.

    Returns:
        (dict) `action` and `observation.state` as `(frames, dim)` float32 arrays,
            the action columns ordered by the `CTR-REC@v1` position-only `names` so a
            column is addressed by name, never by a hardcoded index.
    """
    names = action_names(dataset.config.bimanual)
    action = np.array(
        [[frame.action[name] for name in names] for frame in dataset.frames], dtype=_FLOAT32
    )
    state = np.array([frame.observation_state for frame in dataset.frames], dtype=_FLOAT32)
    return {ACTION_KEY: action, OBSERVATION_STATE_KEY: state}


def numeric_names(config: RecorderConfig) -> dict[str, tuple[str, ...]]:
    """Return the per-feature channel names, for std-floor and quantile reports.

    Args:
        config: The recorder configuration.

    Returns:
        (dict) Feature key to its ordered channel `names`.
    """
    return {
        ACTION_KEY: action_names(config.bimanual),
        OBSERVATION_STATE_KEY: observation_state_names(
            config.bimanual, config.use_velocity_and_torque
        ),
    }
