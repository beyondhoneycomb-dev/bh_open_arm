"""The two sides the compatibility gate compares: a checkpoint and a dataset.

`02c` §2.2 names the inputs `checkpoint` and `dataset`; this module gives them a
concrete shape reduced to exactly what the gate reads, built entirely out of the
committed upstream contracts so nothing here re-declares a frozen schema:

- the checkpoint's immutable attachment (`FR-TRN-043`) is the WP-4A-05 `LineageRecord`
  (its element (b) observation config carries the `names` and shapes, its element (a)
  carries the recorded stats hash) plus the WP-4A-04 `NormalizationContract` (the
  serving-side stats hash). Carrying BOTH is what makes `CG-4B-02e` checkable — the
  two hashes are independent sources that a compatible checkpoint reports equal.
- the dataset is the WP-4A-02 `ObservationConfig` (names-canonical, `FR-TRN-061`) plus
  its live statistics, which serving re-hashes to compare against the checkpoint.

The reader methods normalize the two differently-named observation configs (the
lineage config exposes `state_shape`/`action_shape`, the dataset config
`state_dim`/`action_dim`) down to the one comparison the gate makes: the ordered state
`names` and the action width.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.dataset.stats.hashing import StatsInput
from backend.training.lineage.record import LineageRecord
from backend.training.normstats import NormalizationContract
from backend.training.preflight import ObservationConfig


@dataclass(frozen=True)
class CheckpointAttachment:
    """A checkpoint's immutable attachment, reduced to what compatibility reads.

    Bundles the committed WP-4A-05 lineage and WP-4A-04 normalization contract rather
    than re-declaring either. The lineage supplies the trained observation `names` and
    shapes and the element (a) stats hash; the contract supplies the serving-side stats
    hash. `policy_id`, when present, is the LeRobot family the checkpoint was trained
    as, which the gate feeds to the WP-4B-01 matrix.

    Attributes:
        lineage: The WP-4A-05 eight-element lineage record.
        normalization: The WP-4A-04 normalization contract embedded in the checkpoint.
        policy_id: The policy family the checkpoint uses (a WP-4B-01 family id), or
            None to skip the policy axis of the check.
    """

    lineage: LineageRecord
    normalization: NormalizationContract
    policy_id: str | None

    def state_names(self) -> tuple[str, ...]:
        """The trained `observation.state` channel names, in recorded order."""
        return tuple(self.lineage.observation.names)

    def action_dim(self) -> int:
        """The trained `action` width."""
        return self.lineage.observation.action_shape

    def lineage_stats_hash(self) -> str:
        """The stats hash recorded in element (a) of the lineage."""
        return self.lineage.dataset.stats_hash

    def contract_stats_hash(self) -> str:
        """The stats hash the normalization contract was built under."""
        return self.normalization.stats_hash


@dataclass(frozen=True)
class DatasetTarget:
    """The candidate dataset a checkpoint is checked against.

    `observation` is the WP-4A-02 dataset observation config, whose `names` are the
    canonical judgment (`FR-TRN-061`); `stats` is the live statistics serving would
    normalize with — a fitted stats object or a raw `feature -> metric -> array` table
    read back from disk — which the serving gate re-hashes to compare against the
    checkpoint's recorded hash.

    Attributes:
        observation: The WP-4A-02 observation configuration the dataset declares.
        stats: The statistics serving would normalize with, for the stats-hash block.
    """

    observation: ObservationConfig
    stats: StatsInput

    def state_names(self) -> tuple[str, ...]:
        """The dataset's `observation.state` channel names, as declared."""
        return tuple(self.observation.names)

    def action_dim(self) -> int:
        """The dataset's `action` width."""
        return self.observation.action_dim
