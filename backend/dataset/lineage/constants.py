"""Named literals for the reverse-lineage store (WP-3D-04).

Every value here is a decision the store depends on: the SQLite table and column
names the reverse query joins on, the schema generation, and the set of record
fields `02b` §8.2 WP-3D-04 ② requires to be present on every record. They are
named in one place so the schema, the writer and the query cannot drift apart.
"""

from __future__ import annotations

# The store generation. A shape change to the tables is a new generation, checked
# against the value stamped into a database at creation so an old file cannot be
# reopened and silently misread (`02b` §8.2 WP-3D-04 ④, traceability CI).
SCHEMA_VERSION = 1

# The in-memory database path sqlite3 recognises; used by tests and by a caller
# that wants a throwaway store without touching disk.
MEMORY_DATABASE = ":memory:"

# The two tables. `training_run` holds one row per checkpoint-producing training
# run; `run_episode` is the many-to-one map from a run to each episode it consumed.
# The reverse query ("which checkpoints used this episode") is a join over the
# second table, which LeRobot does not maintain — it restores the forward direction
# only (`02b` §8.2 WP-3D-04, the load-bearing invariant).
RUN_TABLE = "training_run"
RUN_EPISODE_TABLE = "run_episode"

# The `training_run` columns, in declaration order. These are the WP-3D-04 record
# fields (② every required record field is present): stamped `repo_id`, dataset
# content hash, revision, stats hash, the `use_velocity_and_torque` switch, state
# dimension, the encoder settings, the channel-selection state (③), and the
# checkpoint identity (`output_dir` + step). `episodes` is not a column here — it is
# the `run_episode` table, because the reverse query keys on it.
RUN_COLUMNS = (
    "repo_id",
    "dataset_content_hash",
    "revision",
    "stats_hash",
    "use_velocity_and_torque",
    "state_dim",
    "encoder_settings",
    "channel_selection",
    "output_dir",
    "step",
)

# The names of every field a complete lineage record carries, for the ② presence
# check. `episodes` and `channels` are members that map to the `run_episode` table
# and the `channel_selection` column respectively, so they are listed by their
# record-field name rather than their storage column.
REQUIRED_RECORD_FIELDS = (
    "repo_id",
    "dataset_content_hash",
    "revision",
    "episodes",
    "stats_hash",
    "use_velocity_and_torque",
    "state_dim",
    "encoder_settings",
    "channels",
    "output_dir",
    "step",
)

# The keys of the channel-selection JSON blob (③). Position is always a training
# input; velocity and torque are only available under `use_velocity_and_torque`;
# depth is an image channel, independent of the state width.
CHANNEL_POSITION = "pos"
CHANNEL_VELOCITY = "vel"
CHANNEL_TORQUE = "torque"
CHANNEL_DEPTH = "depth"
CHANNEL_KEYS = (CHANNEL_POSITION, CHANNEL_VELOCITY, CHANNEL_TORQUE, CHANNEL_DEPTH)

# SQLite does not enforce foreign keys unless asked per connection; the cascade
# from `training_run` to `run_episode` relies on it, so it is turned on at open.
FOREIGN_KEYS_PRAGMA = "PRAGMA foreign_keys = ON"
