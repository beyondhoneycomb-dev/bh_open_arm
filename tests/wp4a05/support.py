"""Builders that ground the WP-4A-05 acceptance in the synthetic dataset fixture.

`THE ONE RULE` for this band: the offline acceptance rides on the real synthetic
48-dim fixture and the committed upstream, not on mocks. So these helpers assemble a
`LineageRecord` whose element (a) `stats_hash` is the committed
`NormalizationContract` hash of a real fit, whose observation names are the recorder
contract's own `observation_state_names`, and whose stamped `repo_id` comes from the
recorder's `stamp_repo_id`. A record built this way is the lineage of a checkpoint
that trained on that fixture — the same discipline as the WP-3D-04 and WP-4A-04
supports it composes with.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import backend.dataset.stats as stats
from backend.dataset.stats.episodes import numeric_episode_data, numeric_features
from backend.recorder.embed import stamp_repo_id
from backend.training.degenerate import (
    DegenerateChoice,
    DegenerateDecision,
    DegenerateFinding,
    NormMode,
)
from backend.training.lineage import (
    CONTAINER_NOT_USED,
    LineageRecord,
    MergeHistoryEntry,
    ObservationConfig,
    VersionPins,
)
from backend.training.lineage.recorder import LineageRecorder
from backend.training.normstats import NormalizationContract, build_normalization_contract
from backend.training.preflight import Component
from contracts.fixtures.synthetic_dataset import build_synthetic_dataset
from contracts.recorder import observation_state_names

# A fixed stamp instant so a fixture `repo_id` is deterministic across runs.
_STAMP_MOMENT = datetime(2026, 7, 23, 10, 0, 0)
_BASE_REPO_ID = "openarm/pick_place"
_FRAMES = 12


def fixture_repo_id(base: str = _BASE_REPO_ID) -> str:
    """A stamped training-dataset `repo_id`, from the recorder's own stamp."""
    return stamp_repo_id(base, _STAMP_MOMENT)


def fit_stats(count: int = 3, frames: int = _FRAMES) -> stats.NormalizationStats:
    """Fit a deterministic train normalization from `count` synthetic episodes."""
    features = numeric_features(build_synthetic_dataset(0, frames).config)
    episodes = [
        numeric_episode_data(build_synthetic_dataset(index, frames)) for index in range(count)
    ]
    return stats.fit_normalization_stats(episodes, features)


def fixture_contract() -> NormalizationContract:
    """The committed normalization contract for the fixture's train fit."""
    return build_normalization_contract(fit_stats())


def fixture_observation() -> ObservationConfig:
    """The 48-dim bimanual velocity-and-torque observation config of the fixture."""
    names = observation_state_names(True, True)
    return ObservationConfig(
        use_velocity_and_torque=True,
        state_shape=len(names),
        action_shape=len(names),
        names=names,
    )


def sample_decision() -> DegenerateDecision:
    """One WP-4A-03 degenerate decision, for a non-empty element (h)."""
    finding = DegenerateFinding(
        channel_name="left_joint_2.vel",
        joint="left_joint_2",
        component=Component.VEL,
        norm_mode=NormMode.MEAN_STD,
        statistic=0.0,
        threshold=1e-3,
        amplification_estimate=1e6,
    )
    return DegenerateDecision(
        finding=finding, choice=DegenerateChoice.EXCLUDE, rationale="stationary"
    )


def fixture_record(
    episodes: Sequence[int] = (0, 1, 2),
    repo_id: str | None = None,
    revision: str = "rev-0001",
    container_digest: str = CONTAINER_NOT_USED,
    degenerate_decisions: Sequence[DegenerateDecision] | None = None,
    contract: NormalizationContract | None = None,
    source_session: str | None = None,
) -> LineageRecord:
    """Build a complete eight-element record grounded in the fixture.

    Args:
        episodes: The merged-dataset episode indices the run consumed; encoded as an
            identity merge map so element (c) yields exactly these.
        repo_id: The dataset's stamped `repo_id`; defaults to the fixture's.
        revision: The dataset revision.
        container_digest: Element (g); defaults to the explicit not-used value.
        degenerate_decisions: Element (h); defaults to one decision.
        contract: The normalization contract whose `stats_hash` becomes element (a);
            defaults to the fixture contract.
        source_session: The element (c) source session; defaults to the repo_id.

    Returns:
        (LineageRecord) A full, valid record for the fixture checkpoint.
    """
    repo = repo_id if repo_id is not None else fixture_repo_id()
    used_contract = contract if contract is not None else fixture_contract()
    decisions = (
        list(degenerate_decisions) if degenerate_decisions is not None else [sample_decision()]
    )
    return LineageRecorder.build_record(
        repo_id=repo,
        revision=revision,
        info_hash="info-hash-0001",
        normalization_contract=used_contract,
        observation=fixture_observation(),
        merge_history=[
            MergeHistoryEntry(
                source_session=source_session if source_session is not None else repo,
                episode_index_map={index: index for index in episodes},
            )
        ],
        train_config={"policy": {"type": "act"}, "steps": 1000, "batch_size": 8},
        pins=VersionPins(
            code_sha="c1fba262bd6c456df91ffaebea838905049f1e31",
            lerobot_version="0.6.0",
            container_digest=container_digest,
        ),
        degenerate_decisions=decisions,
    )
