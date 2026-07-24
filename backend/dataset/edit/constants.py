"""Named layout, hashing and policy constants for the CoW edit band (WP-3D-02, `02b` §8).

The values here are the on-disk names the edit engine joins on, the columns an
episode's content identity is hashed over, and the sentinel a rejected edit leaves
behind. They are not tunable thresholds: `02b` §8.2 WP-3D-02 fixes the *behaviour*
(copy-on-write, 100% cross-check, abort on mismatch), and these constants are the
concrete names that behaviour is expressed in.
"""

from __future__ import annotations

# The per-frame columns an episode's content identity is hashed over. Deliberately
# excludes every index column that a renumber rewrites — `episode_index`, `index`,
# `task_index`, `timestamp` — so an episode hashes to the same value before and after
# it is moved. `action` and `observation.state` are the recorded content; `frame_index`
# pins the intra-episode order so a dropped or reordered frame changes the hash. The
# join the whole remap rests on is that this hash survives renumbering (`02b` §8.2 ①).
IDENTITY_COLUMNS = ("frame_index", "action", "observation.state")

# The two columns at least one of which must be present for an episode to be
# identifiable at all: without recorded content there is nothing to hash a label to.
IDENTITY_CONTENT_COLUMNS = ("action", "observation.state")

# LeRobot's per-episode metadata keys the edit engine reads to locate an episode's
# data shard and its frame span. Consumed by reference from LeRobot 0.6.0's dataset
# metadata; redefined nowhere.
EPISODE_LENGTH_KEY = "length"
EPISODE_DATA_CHUNK_KEY = "data/chunk_index"
EPISODE_DATA_FILE_KEY = "data/file_index"

# The parquet columns that carry an episode's identity within a data shard.
EPISODE_INDEX_COLUMN = "episode_index"
FRAME_INDEX_COLUMN = "frame_index"

# The sentinel a rejected edit writes into its output so the half-formed dataset is
# never mistaken for a READY training input (`02b` §8.2 WP-3D-02 ②). Its presence is
# the machine-readable statement "this output is INVALID"; WP-3D-05's integrity gate
# also refuses it, but the edit engine marks it at the source rather than relying on a
# later checker to notice.
INVALID_MARKER_NAME = "meta/EDIT_INVALID.json"

# Copy-on-write disk headroom: an edit holds the original and the new version on disk
# at once (`02b` §8.2 WP-3D-02 ⑥, §8.3), so the engine refuses to start unless the
# output filesystem has at least the original's size free. The new version is at most
# the original's size (a delete shrinks it, a split partitions it, an in-place copy
# equals it), so the original's own size is a safe required-free floor.
COW_REQUIRED_FREE_MULTIPLE = 1.0

# The default output-name key for a single-output edit. Split is the only multi-output
# operation and keys its outputs by split name; every other operation writes one
# dataset, filed here.
SINGLE_OUTPUT_KEY = "output"
