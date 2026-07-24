"""Named literals for the FR-TRN-054 lineage record and its bidirectional index.

Every value here is a decision the record schema, the recorder or the query
depends on: the eight element keys of the immutable snapshot (`02c` §1.5,
`FR-TRN-054` (a)-(h)), the on-disk filenames of the two composed stores, and the
explicit sentinel that keeps container-not-adopted a recorded value rather than an
absent field. They are named in one place so the writer and the reader cannot
drift apart, and so the eight-element presence check reads its element set from the
same list the serialiser writes.
"""

from __future__ import annotations

# The snapshot generation. A shape change to the serialised record is a new
# generation, stamped into every snapshot so a reader can refuse an incompatible
# one rather than misread old bytes (mirrors WP-3D-04's `SCHEMA_VERSION`).
SNAPSHOT_SCHEMA_VERSION = 1

# The two composed stores under a lineage directory. `index.sqlite` is the
# WP-3D-04 reverse index reused for the bidirectional query (`FR-OPS-070`); the
# snapshot file is this package's immutable eight-element record store.
REVERSE_INDEX_FILENAME = "index.sqlite"
SNAPSHOT_FILENAME = "snapshots.json"

# The explicit value recorded for element (g) when no container was adopted
# (container adoption is `FR-OPS-062`, a decision-pending item). `02c` §1.5 negative
# branch is emphatic: a lineage that records container-not-used as an explicit value
# PASSES, one that omits the field FAILS — field absence is not the same statement as
# not-used (CG-4A-05a).
CONTAINER_NOT_USED = "container not used"

# The eight element keys of the serialised record, in `FR-TRN-054` (a)-(h) order.
# (a) dataset identity, (b) observation config, (c) session merge history,
# (d) the full train_config.json, (e) training-code git SHA, (f) LeRobot version,
# (g) container image digest, (h) degenerate-channel handling decisions.
DATASET_KEY = "dataset"
OBSERVATION_KEY = "observation"
MERGE_HISTORY_KEY = "merge_history"
TRAIN_CONFIG_KEY = "train_config"
CODE_SHA_KEY = "code_sha"
LEROBOT_VERSION_KEY = "lerobot_version"
CONTAINER_DIGEST_KEY = "container_digest"
DEGENERATE_DECISIONS_KEY = "degenerate_decisions"

# The eight elements that must all be present, in order. A missing element BLOCKs
# (CG-4A-05a): the record's whole purpose is reproduction, and a snapshot missing
# any one of these cannot reproduce the training run it claims to describe.
RECORD_ELEMENT_KEYS = (
    DATASET_KEY,
    OBSERVATION_KEY,
    MERGE_HISTORY_KEY,
    TRAIN_CONFIG_KEY,
    CODE_SHA_KEY,
    LEROBOT_VERSION_KEY,
    CONTAINER_DIGEST_KEY,
    DEGENERATE_DECISIONS_KEY,
)

# The sub-fields of element (a), the dataset identity. `repo_id` + git `revision` +
# `info.json` hash + `stats.json` hash — the four that `FR-TRN-054` (a) names, and
# no more (the WP-3D-04 reverse-index content-hash key is a recording parameter,
# not part of this snapshot, so it is not listed here).
DATASET_REPO_ID_KEY = "repo_id"
DATASET_REVISION_KEY = "revision"
DATASET_INFO_HASH_KEY = "info_hash"
DATASET_STATS_HASH_KEY = "stats_hash"

# The sub-fields of element (b), the observation config the policy consumed.
OBSERVATION_UVT_KEY = "use_velocity_and_torque"
OBSERVATION_STATE_SHAPE_KEY = "state_shape"
OBSERVATION_ACTION_SHAPE_KEY = "action_shape"
OBSERVATION_NAMES_KEY = "names"

# The sub-fields of one element (c) merge-history entry: the source session and the
# map from that session's episode indices to the merged dataset's episode indices
# (`FR-TRN-071`). The union of the map's values across entries is the concrete
# episode list the reverse index keys on — the join between (c) and `FR-OPS-070`.
MERGE_SOURCE_SESSION_KEY = "source_session"
MERGE_EPISODE_INDEX_MAP_KEY = "episode_index_map"

# The top-level keys of the snapshot JSON file: the checkpoint-keyed record map and
# the eval-report-to-checkpoint descendant map the stale engine propagates through.
SNAPSHOTS_KEY = "snapshots"
EVAL_REPORTS_KEY = "eval_reports"
SCHEMA_VERSION_KEY = "schema_version"

# The eval-report descendant link fields (CG-4A-05d): a report id and the
# checkpoint identity it was produced from.
EVAL_REPORT_OUTPUT_DIR_KEY = "output_dir"
EVAL_REPORT_STEP_KEY = "step"

# The LeRobot distribution whose installed version is element (f). Pinned to the
# committed lockfile version (`0.6.0`); captured at record time, never hard-coded
# as a value, so a version bump is recorded rather than silently misattributed.
LEROBOT_DISTRIBUTION = "lerobot"
