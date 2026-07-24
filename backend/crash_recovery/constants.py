"""Named literals for the crash/resume drill (WP-3C-07, `02b` §7 WP-3C-07).

Every value here names a decision the drill depends on: the LeRobot v3.0 on-disk
layout the recorder wrote (`meta/info.json`, the packed `data/chunk-*/file-*.parquet`,
the per-episode `meta/episodes/*`, the `videos/*` tree), the packed-parquet column
names the recovery means index by, the `info.json` counters a rebuild restates, and
the session-journal file the resume path restores from. They are consumed from the
recorder's *output* — WP-3C-07 reads these artefacts as files, it does not import the
recorder's writing API (`02b` §7 WP-3C-07 참조근거, `06` §5.6).
"""

from __future__ import annotations

# The recorder writes a LeRobot v3.0 dataset (`info.json` `codebase_version`
# "v3.0"). These are the layout subtrees the drill reads and the recovery means
# repair; the templates mirror `info.json`'s own `data_path`/`video_path`.
INFO_RELATIVE_PATH = "meta/info.json"
DATA_DIR = "data"
EPISODES_META_DIR = "meta/episodes"
VIDEOS_DIR = "videos"
PARQUET_FILE_GLOB = "file-*.parquet"
MP4_FILE_GLOB = "file-*.mp4"
PARQUET_SUFFIX = ".parquet"
MP4_SUFFIX = ".mp4"

# The v3.0 packed path templates (mirror `info.json`'s own `data_path`/`video_path`).
# `referenced_video_files` rebuilds a segment path from an episode's chunk/file index
# through the video template; the recovery means write repaired data through the data
# template. Named here so the one `{:03d}` packing rule is not restated per call site.
DATA_SEGMENT_TEMPLATE = "data/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet"
EPISODES_SEGMENT_TEMPLATE = "meta/episodes/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet"
VIDEO_SEGMENT_TEMPLATE = "videos/{video_key}/chunk-{chunk_index:03d}/file-{file_index:03d}.mp4"

# The packing name prefixes a segment path carries; a rebuild parses the chunk/file
# index back out of a path through these.
CHUNK_DIR_PREFIX = "chunk-"
FILE_STEM_PREFIX = "file-"

# The suffixes of the two `meta/episodes` video-locator column families, e.g.
# `videos/<key>/chunk_index` and `videos/<key>/file_index`. A video file no episode
# locates through these is unmatched (WP-3C-07 means 2).
VIDEO_CHUNK_COLUMN_SUFFIX = "/chunk_index"
VIDEO_FILE_COLUMN_SUFFIX = "/file_index"

# The session journal: WP-3C-07 ④/⑤. A crash-surviving record of the stamped
# `repo_id`, task, episode counter and config, written beside the dataset so a
# resume restores the *existing* stamped id without re-stamping it. It lives under
# `meta/` next to the recorder's own metadata but is owned by this WP, never the
# recorder.
JOURNAL_RELATIVE_PATH = "meta/session_journal.json"
JOURNAL_SCHEMA_VERSION = 1
JOURNAL_ENCODING = "utf-8"

# Columns of the packed data parquet the recorder writes. `episode_index` groups
# the rows of one episode; the truncate and rebuild means index by it. `index` is
# the global row counter a rebuild renumbers so the packed file stays contiguous.
EPISODE_INDEX_COLUMN = "episode_index"
FRAME_INDEX_COLUMN = "frame_index"
INDEX_COLUMN = "index"

# Columns of `meta/episodes/*` the rebuild means restates. These are the minimal
# per-episode records a downstream reader needs to locate an episode's rows in the
# packed data parquet; the per-episode stats columns are NOT recomputed here (that
# is WP-3D-03's `compute_stats`), and the rebuild says so rather than inventing them.
EPISODE_LENGTH_COLUMN = "length"
EPISODE_TASKS_COLUMN = "tasks"
EPISODE_FROM_INDEX_COLUMN = "dataset_from_index"
EPISODE_TO_INDEX_COLUMN = "dataset_to_index"
EPISODE_DATA_CHUNK_COLUMN = "data/chunk_index"
EPISODE_DATA_FILE_COLUMN = "data/file_index"
EPISODE_META_CHUNK_COLUMN = "meta/episodes/chunk_index"
EPISODE_META_FILE_COLUMN = "meta/episodes/file_index"

# `info.json` counters a rebuild restates so the metadata agrees with the packed
# data after a partial episode is truncated.
INFO_TOTAL_EPISODES_KEY = "total_episodes"
INFO_TOTAL_FRAMES_KEY = "total_frames"
INFO_SPLITS_KEY = "splits"
INFO_VIDEO_PATH_KEY = "video_path"
INFO_FPS_KEY = "fps"
INFO_TRAIN_SPLIT_KEY = "train"

# The recovery means write repaired parquets copy-on-write: a new file beside the
# original, atomically renamed over it, so a crash *during recovery* never leaves a
# second footerless file. This is the scratch suffix for the pre-rename copy.
RECOVERY_SCRATCH_SUFFIX = ".recovering"

# The reasons a crash holds an episode for human judgment. The footerless (SIGKILL)
# case reuses the recorder band's own `AbortReason.CRASH_FOOTERLESS_PARQUET`; these two
# name the other phase-1 faults, which do not correspond to a recorder-band reason. A
# reason is mandatory — an unexplained hold is the WP-3B-12 FAIL_BLOCKING defect — and
# it is never empty.
PENDING_REASON_DISK_FULL = "crash-disk-full-partial-episode"
PENDING_REASON_NETWORK_CUT = "crash-network-cut-orphaned-video"

# The salvage file a readable partial episode's rows are isolated to, for the human's
# save/discard decision. It lives in the recorder band's quarantine directory.
SALVAGE_PARQUET_TEMPLATE = "episode_{episode_index}_salvage.parquet"

# The `strftime` stamp the recorder appends to a `repo_id` (mirrors
# `REPO_ID_STAMP_FORMAT` in the recorder embed). The drill never *applies* this — it
# is named here only so the no-re-stamp assertion can recognise a doubly-stamped id
# (two trailing stamp groups) as the divergence WP-3C-07 ⑤ forbids.
REPO_ID_STAMP_REGEX = r"_\d{8}_\d{6}$"
