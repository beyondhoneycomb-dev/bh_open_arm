"""The lineage record — one training run's tie to the dataset and episodes it used.

`02b` §8.2 WP-3D-04 fixes the field set: a record is a stamped `repo_id`, the
dataset content hash, the revision, the episodes consumed, the stats hash, the
`use_velocity_and_torque` switch, the observation state dimension, the encoder
settings, the channel-selection state, and the checkpoint identity (`output_dir`
plus step). Those field names line up with LeRobot's `train_config.json`
serialisation (`dataset.repo_id`, `dataset.revision`, `dataset.episodes`,
`output_dir`, `steps`); the store derives the reverse direction LeRobot does not.

The record validates itself before the store will accept it. The load-bearing rule
(WP-3D-04 negative branch): a record with no episode mapping — an empty `episodes`
tuple — is `FAIL_BLOCKING`, because a checkpoint recorded with no episodes is a
lineage hole that the reverse query can never fill (a label would stick to no
episode at all). Presence of every field (②) and consistency of the channel
selection with the state width (③) are enforced here too.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from backend.dataset.lineage.channels import ChannelSelection, ChannelSelectionError
from backend.dataset.lineage.constants import REQUIRED_RECORD_FIELDS
from backend.dataset.lineage.source import LineageSourceError, validate_dataset_repo_id


class LineageError(ValueError):
    """Raised when a lineage record is incomplete or internally inconsistent.

    The `FAIL_BLOCKING` cases (WP-3D-04 negative branch): a missing required field,
    an empty episode mapping, a non-monotone or negative episode index, a
    non-positive state dimension, a negative step, or a channel selection the state
    width contradicts. Every one leaves the reverse query unable to answer honestly,
    so the store refuses the record rather than storing a half-truth.
    """


@dataclass(frozen=True)
class LineageRecord:
    """One checkpoint-producing training run and the dataset slice it consumed.

    Attributes:
        repo_id: The training dataset's stamped `repo_id` (`dataset.repo_id`).
        dataset_content_hash: The content hash of the dataset version used — the
            copy-on-write-stable identity, so an edited dataset with a new hash is a
            distinct source and old lineage still points at the old bytes.
        revision: The dataset revision (`dataset.revision`).
        episodes: The episode indices the run consumed (`dataset.episodes`, resolved
            to a concrete list). Non-empty: an empty mapping is `FAIL_BLOCKING`.
        stats_hash: The content hash of the normalisation statistics the run fit,
            recorded so an inference-time stats mismatch can be detected (WP-3D-03).
        use_velocity_and_torque: The dataset's recorder switch; fixes which channels
            the selection may include.
        state_dim: The `observation.state` width the policy consumed.
        encoder_settings: The video/image encoder settings the dataset used, stored
            as a JSON-serialisable mapping (empty for a state-only dataset).
        channels: The channel-selection state (③), reproducible off `CTR-REC@v1`.
        output_dir: The training run's output directory (`output_dir`).
        step: The checkpoint step within that run; `output_dir` + step is the
            checkpoint's identity.
    """

    repo_id: str
    dataset_content_hash: str
    revision: str
    episodes: tuple[int, ...]
    stats_hash: str
    use_velocity_and_torque: bool
    state_dim: int
    encoder_settings: Mapping[str, Any]
    channels: ChannelSelection
    output_dir: str
    step: int

    def validate(self) -> None:
        """Refuse a record that would leave a lineage hole.

        Raises:
            LineageError: On a missing field, an empty or malformed episode mapping,
                a non-positive state dimension, a negative step, or a channel
                selection inconsistent with the state width.
        """
        self._check_fields_present()
        self._check_episodes()
        if self.state_dim <= 0:
            raise LineageError(f"state_dim must be positive, got {self.state_dim}")
        if self.step < 0:
            raise LineageError(f"step must be non-negative, got {self.step}")
        # The source-identity and channel checks raise their own error types; at the
        # record boundary they are all one thing — an invalid record — so they are
        # surfaced as `LineageError` and a caller catches exactly one type.
        try:
            validate_dataset_repo_id(self.repo_id)
            # A channel selection the state width contradicts is not reproducible,
            # which is itself a broken lineage mapping (③), so it is refused here.
            self.channels.validate(self.use_velocity_and_torque, self.state_dim)
        except (LineageSourceError, ChannelSelectionError) as invalid:
            raise LineageError(str(invalid)) from invalid

    def _check_fields_present(self) -> None:
        """Verify every required field carries a value (WP-3D-04 ②).

        Raises:
            LineageError: When a string field is empty; a missing dataclass field is
                already a construction error, so this catches the empty-value case
                the type system cannot.
        """
        empty = [
            field
            for field in REQUIRED_RECORD_FIELDS
            if isinstance(getattr(self, field), str) and not getattr(self, field).strip()
        ]
        if empty:
            raise LineageError(f"required record fields are empty: {sorted(empty)}")

    def _check_episodes(self) -> None:
        """Verify the episode mapping is present, ascending and non-negative.

        Raises:
            LineageError: On an empty mapping (`FAIL_BLOCKING`), a negative index, or
                a duplicate/unsorted list that would make the reverse query ambiguous.
        """
        if not self.episodes:
            raise LineageError(
                "episodes is empty; a checkpoint with no episode mapping is FAIL_BLOCKING "
                "(the reverse query could never attribute it to any episode)"
            )
        if any(index < 0 for index in self.episodes):
            raise LineageError(f"episode indices must be non-negative, got {self.episodes}")
        if list(self.episodes) != sorted(set(self.episodes)):
            raise LineageError(
                f"episodes must be strictly ascending and unique, got {self.episodes}"
            )

    def encoder_settings_json(self) -> str:
        """Serialise the encoder settings deterministically for storage.

        Returns:
            (str) Sorted-key JSON of the encoder settings mapping.
        """
        return json.dumps(dict(self.encoder_settings), sort_keys=True)
