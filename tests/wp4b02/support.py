"""Builders that ground the WP-4B-02 acceptance in the real synthetic fixture.

`THE ONE RULE` for this band: the gate must genuinely fire, so the acceptance rides on
the committed 48-dim synthetic dataset and the committed upstream — a real train fit
whose `NormalizationContract` hash is the checkpoint's recorded hash, real recorder
`names`, and a WP-4A-05 `LineageRecord` assembled by the committed recorder. A
checkpoint built this way is the attachment of a run that trained on that fixture; a
dataset built this way is a candidate that may or may not match it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import lru_cache

import numpy as np

import backend.dataset.stats as stats
from backend.compat.checkpoint_dataset import CheckpointAttachment, DatasetTarget
from backend.dataset.stats.episodes import numeric_episode_data, numeric_features
from backend.training.lineage import (
    CONTAINER_NOT_USED,
    MergeHistoryEntry,
    VersionPins,
)
from backend.training.lineage import (
    ObservationConfig as LineageObservation,
)
from backend.training.lineage.recorder import LineageRecorder
from backend.training.normstats import NormalizationContract, build_normalization_contract
from backend.training.preflight import ObservationConfig as DatasetObservation
from contracts.fixtures.synthetic_dataset import build_synthetic_dataset
from contracts.prim import BIMANUAL_ACTION_DIM
from contracts.recorder import TORQUE_SUFFIX, observation_state_names

_FRAMES = 12
_REPO_ID = "openarm/pick_place"
_REVISION = "rev-0001"

# The two fixture layouts, both bimanual: the full 48-dim pos+vel+torque recording and
# the 16-dim position-only subset. A position-only checkpoint fed the full dataset (and
# the reverse) is the CG-4B-02a/b pairing.
FULL_NAMES = observation_state_names(True, True)
POS_ONLY_NAMES = observation_state_names(True, False)


@lru_cache(maxsize=1)
def fit_stats(count: int = 3) -> stats.NormalizationStats:
    """Fit a deterministic train normalization from `count` synthetic episodes."""
    features = numeric_features(build_synthetic_dataset(0, _FRAMES).config)
    episodes = [
        numeric_episode_data(build_synthetic_dataset(index, _FRAMES)) for index in range(count)
    ]
    return stats.fit_normalization_stats(episodes, features)


def fixture_contract() -> NormalizationContract:
    """The committed normalization contract for the fixture's train fit."""
    return build_normalization_contract(fit_stats())


def one_bit_changed_stats() -> dict[str, dict[str, np.ndarray]]:
    """The fixture stats table with a single value perturbed — a different content hash.

    Copies the committed fit's per-feature table and nudges one element, so the table
    re-hashes to a different digest than the checkpoint recorded (CG-4B-02c). The change
    is deliberately tiny: the block must fire on any difference, not only a large one.
    """
    table: dict[str, dict[str, np.ndarray]] = {
        feature: {
            metric: np.array(value, dtype=np.float64, copy=True)
            for metric, value in metrics.items()
        }
        for feature, metrics in fit_stats().per_feature.items()
    }
    feature = sorted(table)[0]
    metric = sorted(table[feature])[0]
    table[feature][metric].flat[0] += 1e-9
    return table


def dataset_observation(
    names: Sequence[str], action_dim: int = BIMANUAL_ACTION_DIM
) -> DatasetObservation:
    """A WP-4A-02 dataset observation config for the given state names."""
    return DatasetObservation(
        use_velocity_and_torque=any(name.endswith(TORQUE_SUFFIX) for name in names),
        state_dim=len(names),
        action_dim=action_dim,
        names=tuple(names),
        bimanual=action_dim == BIMANUAL_ACTION_DIM,
    )


def dataset_target(
    names: Sequence[str] = FULL_NAMES,
    action_dim: int = BIMANUAL_ACTION_DIM,
    stats_table: stats.NormalizationStats | Mapping[str, Mapping[str, np.ndarray]] | None = None,
) -> DatasetTarget:
    """A candidate dataset: an observation config plus live statistics.

    Defaults to the full 48-dim recording with the committed fit's statistics, i.e. the
    dataset a compatible checkpoint was trained on.
    """
    return DatasetTarget(
        observation=dataset_observation(names, action_dim),
        stats=fit_stats() if stats_table is None else stats_table,
    )


def checkpoint_attachment(
    names: Sequence[str] = FULL_NAMES,
    action_dim: int = BIMANUAL_ACTION_DIM,
    contract: NormalizationContract | None = None,
    policy_id: str | None = None,
    episodes: Sequence[int] = (0, 1, 2),
) -> CheckpointAttachment:
    """A checkpoint attachment grounded in a committed lineage record and contract.

    The lineage's element (a) `stats_hash` is taken from the same contract by the
    committed recorder, so a checkpoint built here reports an equal lineage and contract
    hash (the CG-4B-02e precondition) unless the caller deliberately splits them.
    """
    used_contract = contract if contract is not None else fixture_contract()
    lineage = LineageRecorder.build_record(
        repo_id=_REPO_ID,
        revision=_REVISION,
        info_hash="info-hash-0001",
        normalization_contract=used_contract,
        observation=LineageObservation(
            use_velocity_and_torque=any(name.endswith(TORQUE_SUFFIX) for name in names),
            state_shape=len(names),
            action_shape=action_dim,
            names=tuple(names),
        ),
        merge_history=[
            MergeHistoryEntry(
                source_session=_REPO_ID, episode_index_map={index: index for index in episodes}
            )
        ],
        train_config={"policy": {"type": policy_id or "act"}, "steps": 1000},
        pins=VersionPins(
            code_sha="c1fba262bd6c456df91ffaebea838905049f1e31",
            lerobot_version="0.6.0",
            container_digest=CONTAINER_NOT_USED,
        ),
        degenerate_decisions=[],
    )
    return CheckpointAttachment(lineage=lineage, normalization=used_contract, policy_id=policy_id)
