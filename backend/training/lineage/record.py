"""The immutable eight-element lineage snapshot — `FR-TRN-054` (a)-(h), 1:1.

`02c` §1.5 fixes the schema exactly, and the rule is unusually strict: the record's
eight elements are `FR-TRN-054` (a) through (h), and the interface contract invents
no field and omits none. This module is that schema — a frozen `LineageRecord` whose
members are the eight elements, plus the value objects (a)-(c) decompose into — and
the validation that makes the strictness real: a record missing any element BLOCKs
(CG-4A-05a), because the record's purpose is reproduction and a snapshot missing an
element cannot reproduce the run it claims to describe.

The eight elements and their homes here:

    (a) dataset identity      -> DatasetLineage{repo_id, revision, info_hash, stats_hash}
    (b) observation config    -> ObservationConfig{use_velocity_and_torque, state_shape,
                                                    action_shape, names}
    (c) session merge history -> tuple[MergeHistoryEntry{source_session, episode_index_map}]
    (d) train_config.json     -> train_config (the FULL document, `02c` §1.5 대가:
                                  reproduction needs the whole config, not a summary)
    (e) training-code git SHA -> pins.code_sha
    (f) LeRobot version       -> pins.lerobot_version
    (g) container digest      -> pins.container_digest (explicit not-used, never absent)
    (h) degenerate decisions  -> degenerate_decisions (WP-4A-03's DegenerateDecision,
                                  imported, not redefined)

Element (h) reuses `backend.training.degenerate.DegenerateDecision` unchanged: that
type is WP-4A-03's owned (h) slice, and re-declaring it here would fork the one
schema `02c` §1.3 froze. An empty decision tuple is a present element — a positive
statement that degeneracy was checked and none was found — not a missing one; a
`None` decisions field is the missing case that BLOCKs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from backend.training.degenerate import DegenerateDecision
from backend.training.lineage.constants import (
    CODE_SHA_KEY,
    CONTAINER_DIGEST_KEY,
    DATASET_INFO_HASH_KEY,
    DATASET_KEY,
    DATASET_REPO_ID_KEY,
    DATASET_REVISION_KEY,
    DATASET_STATS_HASH_KEY,
    DEGENERATE_DECISIONS_KEY,
    LEROBOT_VERSION_KEY,
    MERGE_EPISODE_INDEX_MAP_KEY,
    MERGE_HISTORY_KEY,
    MERGE_SOURCE_SESSION_KEY,
    OBSERVATION_ACTION_SHAPE_KEY,
    OBSERVATION_KEY,
    OBSERVATION_NAMES_KEY,
    OBSERVATION_STATE_SHAPE_KEY,
    OBSERVATION_UVT_KEY,
    TRAIN_CONFIG_KEY,
)
from backend.training.lineage.pins import VersionPins


class LineageRecordError(ValueError):
    """Raised when a lineage record is missing an element or one is malformed.

    Every case is `FAIL_BLOCKING` (CG-4A-05a): a missing element, an empty
    dataset-identity field, an empty observation, an empty merge history, an empty
    train_config, a blank version pin, or a container digest left absent rather than
    recorded as an explicit value. The record's purpose is reproduction, so an
    incomplete record is refused rather than stored as a half-truth.
    """


@dataclass(frozen=True)
class DatasetLineage:
    """Element (a): the identity of the dataset version a run trained on.

    Attributes:
        repo_id: The dataset's stamped `repo_id` (recorder artefact, WP-3B-11).
        revision: The dataset git revision (`dataset.revision`).
        info_hash: The content hash of the dataset's `info.json` — its structural
            identity (features, shapes, fps, episode/frame counts).
        stats_hash: The content hash of `stats.json`, the normalisation statistics
            the run fit — the committed `stats_content_hash` (WP-4A-04), embedded so
            a later stats change makes descendant checkpoints stale (CG-4A-05d).
    """

    repo_id: str
    revision: str
    info_hash: str
    stats_hash: str

    def to_dict(self) -> dict[str, str]:
        """Serialise the four identity fields deterministically."""
        return {
            DATASET_REPO_ID_KEY: self.repo_id,
            DATASET_REVISION_KEY: self.revision,
            DATASET_INFO_HASH_KEY: self.info_hash,
            DATASET_STATS_HASH_KEY: self.stats_hash,
        }

    @staticmethod
    def from_dict(raw: Mapping[str, Any]) -> DatasetLineage:
        """Rebuild from serialised form; missing keys raise `LineageRecordError`."""
        try:
            return DatasetLineage(
                repo_id=str(raw[DATASET_REPO_ID_KEY]),
                revision=str(raw[DATASET_REVISION_KEY]),
                info_hash=str(raw[DATASET_INFO_HASH_KEY]),
                stats_hash=str(raw[DATASET_STATS_HASH_KEY]),
            )
        except KeyError as missing:
            raise LineageRecordError(f"dataset element is missing key {missing}") from missing


@dataclass(frozen=True)
class ObservationConfig:
    """Element (b): the observation configuration the policy consumed.

    Attributes:
        use_velocity_and_torque: The recorder switch that fixes whether `.vel` and
            `.torque` channels are present at all.
        state_shape: The `observation.state` width the policy saw.
        action_shape: The `action` width.
        names: The `observation.state` channel names, in `CTR-REC@v1` order — the
            exact list a later reproduction reconstructs the state vector from.
    """

    use_velocity_and_torque: bool
    state_shape: int
    action_shape: int
    names: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialise the observation config deterministically."""
        return {
            OBSERVATION_UVT_KEY: self.use_velocity_and_torque,
            OBSERVATION_STATE_SHAPE_KEY: self.state_shape,
            OBSERVATION_ACTION_SHAPE_KEY: self.action_shape,
            OBSERVATION_NAMES_KEY: list(self.names),
        }

    @staticmethod
    def from_dict(raw: Mapping[str, Any]) -> ObservationConfig:
        """Rebuild from serialised form; missing keys raise `LineageRecordError`."""
        try:
            return ObservationConfig(
                use_velocity_and_torque=bool(raw[OBSERVATION_UVT_KEY]),
                state_shape=int(raw[OBSERVATION_STATE_SHAPE_KEY]),
                action_shape=int(raw[OBSERVATION_ACTION_SHAPE_KEY]),
                names=tuple(str(name) for name in raw[OBSERVATION_NAMES_KEY]),
            )
        except KeyError as missing:
            raise LineageRecordError(f"observation element is missing key {missing}") from missing


@dataclass(frozen=True)
class MergeHistoryEntry:
    """One element (c) row: a source session and its episode-index remap.

    `FR-TRN-071` requires that a session merge record, per source, the map from the
    source's episode indices to the merged dataset's episode indices. The union of
    every entry's map values is the concrete episode list the reverse index keys on,
    which is where element (c) meets the `FR-OPS-070` bidirectional query.

    Attributes:
        source_session: The source session's identity (its stamped `repo_id`).
        episode_index_map: `{source_episode_index -> merged_episode_index}` for that
            session. Keys and values are episode indices in the two datasets.
    """

    source_session: str
    episode_index_map: Mapping[int, int]

    def to_dict(self) -> dict[str, Any]:
        """Serialise; the map's integer keys become strings for JSON."""
        return {
            MERGE_SOURCE_SESSION_KEY: self.source_session,
            MERGE_EPISODE_INDEX_MAP_KEY: {
                str(source): int(merged) for source, merged in self.episode_index_map.items()
            },
        }

    @staticmethod
    def from_dict(raw: Mapping[str, Any]) -> MergeHistoryEntry:
        """Rebuild from serialised form; the map's string keys become integers."""
        try:
            raw_map: Mapping[str, Any] = raw[MERGE_EPISODE_INDEX_MAP_KEY]
            return MergeHistoryEntry(
                source_session=str(raw[MERGE_SOURCE_SESSION_KEY]),
                episode_index_map={int(source): int(merged) for source, merged in raw_map.items()},
            )
        except KeyError as missing:
            raise LineageRecordError(f"merge-history entry is missing key {missing}") from missing


@dataclass(frozen=True)
class LineageRecord:
    """The immutable eight-element snapshot of one checkpoint-producing run.

    Frozen because a lineage record is never edited after the fact (`FR-TRN-054`
    immutable snapshot, CG-4A-05b). The eight members are `FR-TRN-054` (a)-(h), 1:1:
    no field is invented and none is omitted.

    Attributes:
        dataset: Element (a) — the dataset version identity.
        observation: Element (b) — the observation configuration.
        merge_history: Element (c) — the per-source session merge history.
        train_config: Element (d) — the FULL `train_config.json`, kept whole so the
            run can be reproduced, not merely summarised (`02c` §1.5, `FR-OPS-071`).
        pins: Elements (e)-(g) — code SHA, LeRobot version, container digest.
        degenerate_decisions: Element (h) — the WP-4A-03 decisions. Empty is a
            present element (checked, none found); `None` is a missing one and BLOCKs.
    """

    dataset: DatasetLineage
    observation: ObservationConfig
    merge_history: tuple[MergeHistoryEntry, ...]
    train_config: Mapping[str, Any]
    pins: VersionPins
    degenerate_decisions: tuple[DegenerateDecision, ...]

    def consumed_episodes(self) -> tuple[int, ...]:
        """The merged-dataset episode indices this run consumed, from element (c).

        Derived from the merge history rather than stored twice: the union of every
        merge entry's `episode_index_map` values is exactly the set of episodes the
        run trained on, so the reverse index is populated from element (c) rather
        than from a second, forkable episode list (`FR-TRN-071` -> `FR-OPS-070`).

        Returns:
            (tuple[int, ...]) The consumed episode indices, ascending and unique.
        """
        merged = {
            merged_index
            for entry in self.merge_history
            for merged_index in entry.episode_index_map.values()
        }
        return tuple(sorted(merged))

    def validate(self) -> None:
        """Refuse a record missing any of the eight elements (CG-4A-05a).

        Raises:
            LineageRecordError: When any element is absent or malformed — a blank
                dataset-identity field, an empty observation, an empty merge history,
                an empty train_config, a blank version pin, an absent container
                digest, or a `None` decisions field.
        """
        self._validate_dataset()
        self._validate_observation()
        self._validate_merge_history()
        self._validate_train_config()
        self._validate_pins()
        self._validate_degenerate_decisions()

    def _validate_dataset(self) -> None:
        """Element (a): every identity field carries a value."""
        empty = [key for key, value in self.dataset.to_dict().items() if not str(value).strip()]
        if empty:
            raise LineageRecordError(f"dataset element (a) has empty field(s): {sorted(empty)}")

    def _validate_observation(self) -> None:
        """Element (b): positive shapes and a non-empty, correctly sized name list."""
        if self.observation.state_shape <= 0:
            raise LineageRecordError(
                f"observation state_shape must be positive, got {self.observation.state_shape}"
            )
        if self.observation.action_shape <= 0:
            raise LineageRecordError(
                f"observation action_shape must be positive, got {self.observation.action_shape}"
            )
        if not self.observation.names:
            raise LineageRecordError("observation element (b) has no channel names")
        if len(self.observation.names) != self.observation.state_shape:
            raise LineageRecordError(
                f"observation names count {len(self.observation.names)} does not equal "
                f"state_shape {self.observation.state_shape}; the state vector is not reproducible"
            )

    def _validate_merge_history(self) -> None:
        """Element (c): at least one source, each with a non-empty episode map."""
        if not self.merge_history:
            raise LineageRecordError(
                "merge_history element (c) is empty; a run consumes at least one source session "
                "(FR-TRN-071), and an empty history leaves the reverse index with no episodes"
            )
        for entry in self.merge_history:
            if not entry.source_session.strip():
                raise LineageRecordError("merge-history element (c) has a blank source_session")
            if not entry.episode_index_map:
                raise LineageRecordError(
                    f"merge-history source {entry.source_session!r} maps no episodes; "
                    "element (c) must record which episodes each source contributed"
                )
        if not self.consumed_episodes():
            raise LineageRecordError(
                "merge_history element (c) yields no consumed episodes; the reverse query "
                "could never attribute this checkpoint to any episode (FAIL_BLOCKING)"
            )

    def _validate_train_config(self) -> None:
        """Element (d): the full train_config is present and non-empty."""
        if not self.train_config:
            raise LineageRecordError(
                "train_config element (d) is empty; the full config is what makes the run "
                "reproducible (02c §1.5 대가: reproduction, not lookup)"
            )

    def _validate_pins(self) -> None:
        """Elements (e)-(g): each pin is a recorded value, container never absent."""
        if not self.pins.code_sha.strip():
            raise LineageRecordError("code_sha element (e) is blank")
        if not self.pins.lerobot_version.strip():
            raise LineageRecordError("lerobot_version element (f) is blank")
        # (g) is the load-bearing negative branch: an empty container digest is an
        # ABSENT field, which BLOCKs. Not-used must be the explicit CONTAINER_NOT_USED
        # value, which is non-empty and passes here (02c §1.5, CG-4A-05a).
        if not self.pins.container_digest.strip():
            raise LineageRecordError(
                "container_digest element (g) is absent; record CONTAINER_NOT_USED as an "
                "explicit value when no container was adopted — field absence is not not-used"
            )

    def _validate_degenerate_decisions(self) -> None:
        """Element (h): the decisions field is present (a tuple), not absent (None).

        An empty tuple is a present element — degeneracy was checked and none found —
        so it passes; a `None` field is the missing element that BLOCKs. Each entry
        must be a WP-4A-03 `DegenerateDecision` so element (h) cannot carry a foreign
        shape.
        """
        if self.degenerate_decisions is None:
            raise LineageRecordError(
                "degenerate_decisions element (h) is absent (None); record the empty tuple to "
                "state that degeneracy was checked and none found — absence is not 'none found'"
            )
        for decision in self.degenerate_decisions:
            if not isinstance(decision, DegenerateDecision):
                raise LineageRecordError(
                    f"degenerate_decisions element (h) carries a non-DegenerateDecision: "
                    f"{type(decision).__name__}"
                )

    def to_dict(self) -> dict[str, Any]:
        """Serialise all eight elements deterministically for the snapshot store.

        Returns:
            (dict) A JSON-serialisable mapping keyed by the eight element keys.
        """
        return {
            DATASET_KEY: self.dataset.to_dict(),
            OBSERVATION_KEY: self.observation.to_dict(),
            MERGE_HISTORY_KEY: [entry.to_dict() for entry in self.merge_history],
            TRAIN_CONFIG_KEY: dict(self.train_config),
            CODE_SHA_KEY: self.pins.code_sha,
            LEROBOT_VERSION_KEY: self.pins.lerobot_version,
            CONTAINER_DIGEST_KEY: self.pins.container_digest,
            DEGENERATE_DECISIONS_KEY: [_decision_to_dict(d) for d in self.degenerate_decisions],
        }

    @staticmethod
    def from_dict(raw: Mapping[str, Any]) -> LineageRecord:
        """Rebuild a record from its serialised form.

        Args:
            raw: A mapping produced by `to_dict`.

        Returns:
            (LineageRecord) The reconstructed record.

        Raises:
            LineageRecordError: When any of the eight element keys is absent.
        """
        missing = [key for key in _REQUIRED_TOP_KEYS if key not in raw]
        if missing:
            raise LineageRecordError(f"snapshot is missing element(s): {sorted(missing)}")
        return LineageRecord(
            dataset=DatasetLineage.from_dict(raw[DATASET_KEY]),
            observation=ObservationConfig.from_dict(raw[OBSERVATION_KEY]),
            merge_history=tuple(
                MergeHistoryEntry.from_dict(entry) for entry in raw[MERGE_HISTORY_KEY]
            ),
            train_config=dict(raw[TRAIN_CONFIG_KEY]),
            pins=VersionPins(
                code_sha=str(raw[CODE_SHA_KEY]),
                lerobot_version=str(raw[LEROBOT_VERSION_KEY]),
                container_digest=str(raw[CONTAINER_DIGEST_KEY]),
            ),
            degenerate_decisions=tuple(
                _decision_from_dict(entry) for entry in raw[DEGENERATE_DECISIONS_KEY]
            ),
        )


_REQUIRED_TOP_KEYS = (
    DATASET_KEY,
    OBSERVATION_KEY,
    MERGE_HISTORY_KEY,
    TRAIN_CONFIG_KEY,
    CODE_SHA_KEY,
    LEROBOT_VERSION_KEY,
    CONTAINER_DIGEST_KEY,
    DEGENERATE_DECISIONS_KEY,
)


def _decision_to_dict(decision: DegenerateDecision) -> dict[str, Any]:
    """Serialise a WP-4A-03 decision, keeping enum members as their string values.

    `dataclasses.asdict` would leave the `Component`/`NormMode`/`DegenerateChoice`
    enum members as objects; JSON needs their `.value`, and the component may be
    `None`. This mirrors WP-4A-03's own `asdict`-then-reconstruct round-trip.
    """
    finding = decision.finding
    return {
        "finding": {
            "channel_name": finding.channel_name,
            "joint": finding.joint,
            "component": None if finding.component is None else finding.component.value,
            "norm_mode": finding.norm_mode.value,
            "statistic": finding.statistic,
            "threshold": finding.threshold,
            "amplification_estimate": finding.amplification_estimate,
        },
        "choice": decision.choice.value,
        "rationale": decision.rationale,
    }


def _decision_from_dict(raw: Mapping[str, Any]) -> DegenerateDecision:
    """Reconstruct a WP-4A-03 decision from its serialised form.

    Reuses WP-4A-03's own enums and `Component` so element (h) round-trips through
    the committed shapes rather than a fork of them.
    """
    from backend.training.degenerate import DegenerateChoice, DegenerateFinding, NormMode
    from backend.training.preflight import Component

    raw_finding: Mapping[str, Any] = raw["finding"]
    component_value = raw_finding["component"]
    finding = DegenerateFinding(
        channel_name=str(raw_finding["channel_name"]),
        joint=str(raw_finding["joint"]),
        component=None if component_value is None else Component(component_value),
        norm_mode=NormMode(raw_finding["norm_mode"]),
        statistic=float(raw_finding["statistic"]),
        threshold=float(raw_finding["threshold"]),
        amplification_estimate=float(raw_finding["amplification_estimate"]),
    )
    return DegenerateDecision(
        finding=finding,
        choice=DegenerateChoice(raw["choice"]),
        rationale=str(raw["rationale"]),
    )
