"""Layout and channel constants for the WP-3D-01 episode viewer.

Two kinds of constant live here, and the distinction is load-bearing:

1. The LeRobot v3.0 *on-disk layout* — `meta/info.json`, the packed
   `data/chunk-*/file-*.parquet`, the per-key `videos/<key>/chunk-*/file-*.mp4`,
   the per-frame depth `images/<key>/episode-*/frame-*.tiff`, and the episode
   metadata columns that locate one episode's row range and video segment inside
   a packed file. This is a storage convention the direct reader must know to
   read a dataset at all; it is *not* our contract. `06` §5.6 names exactly this
   case — a viewer that reads files another tool wrote — as an edge a static
   import graph cannot see, which is why `WP-3D-01` carries a `참조근거` instead
   of importing `contracts.recorder`.

2. The `CTR-REC@v1` unit convention (`.pos`->deg, `.vel`->deg/s, `.torque`->Nm)
   and the per-motor suffixes. The frozen `WP-3A-05` justification records that
   the viewer consumes `CTR-REC@v1` through the `info.json` `names` strings and
   does not statically import `contracts.recorder`; these mirror that convention
   at the one point the direct-read design forces it to live locally. The camera
   identifier and image-key grammar are the exception — those are `CTR-PRIM@v1`
   primitives, consumed by reference from `contracts.prim`, never restated here.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# LeRobot v3.0 on-disk layout (a storage convention, consumed as data)
# ---------------------------------------------------------------------------

# `meta/info.json` — the feature set, fps, and the path templates a dataset was
# written with. A real dataset carries `data_path`/`video_path` here; when it
# does the reader honours them and only falls back to the defaults below.
INFO_RELATIVE_PATH = "meta/info.json"

INFO_FEATURES_KEY = "features"
INFO_FPS_KEY = "fps"
INFO_DATA_PATH_KEY = "data_path"
INFO_VIDEO_PATH_KEY = "video_path"

# The default v3.0 path templates (`lerobot.datasets.utils`), used only when
# `info.json` omits its own. `{chunk_index:03d}`/`{file_index:03d}` pack many
# episodes into one file; the episode metadata resolves which file and which slice.
DEFAULT_DATA_PATH_TEMPLATE = "data/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet"
DEFAULT_VIDEO_PATH_TEMPLATE = "videos/{video_key}/chunk-{chunk_index:03d}/file-{file_index:03d}.mp4"
EPISODES_METADATA_TEMPLATE = "meta/episodes/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet"

# Per-frame image streams (v3.0 stores depth as 16-bit TIFF frames, RGB stills as
# PNG). The viewer probes for these when no packed video file is present.
DEPTH_IMAGE_PATH_TEMPLATE = (
    "images/{image_key}/episode-{episode_index:06d}/frame-{frame_index:06d}.tiff"
)
RGB_IMAGE_PATH_TEMPLATE = (
    "images/{image_key}/episode-{episode_index:06d}/frame-{frame_index:06d}.png"
)

# Episode metadata columns that locate one episode. `dataset_from_index`/
# `dataset_to_index` are the half-open row range into the packed data parquet;
# the video columns are formed per video key at read time.
EPISODE_INDEX_COLUMN = "episode_index"
EPISODE_FROM_INDEX_COLUMN = "dataset_from_index"
EPISODE_TO_INDEX_COLUMN = "dataset_to_index"
EPISODE_LENGTH_COLUMN = "length"
EPISODE_TASKS_COLUMN = "tasks"


def video_from_timestamp_column(video_key: str) -> str:
    """The episode-metadata column holding a video segment's start second."""
    return f"videos/{video_key}/from_timestamp"


def video_to_timestamp_column(video_key: str) -> str:
    """The episode-metadata column holding a video segment's end second."""
    return f"videos/{video_key}/to_timestamp"


def video_chunk_index_column(video_key: str) -> str:
    """The episode-metadata column holding a video segment's chunk index."""
    return f"videos/{video_key}/chunk_index"


def video_file_index_column(video_key: str) -> str:
    """The episode-metadata column holding a video segment's file index."""
    return f"videos/{video_key}/file_index"


# ---------------------------------------------------------------------------
# The per-frame data table (the packed parquet columns a frame carries)
# ---------------------------------------------------------------------------

# The two vector features and the grid time column. `timestamp` is the synthetic
# playback grid `frame_index / fps`, never a capture instant — the axis label and
# `TimeAxis.is_wall_clock` carry that fact to the UI (`FR-DAT-010`).
OBSERVATION_STATE_KEY = "observation.state"
ACTION_KEY = "action"
TIMESTAMP_COLUMN = "timestamp"
FRAME_INDEX_COLUMN = "frame_index"

# The feature-body keys inside one `info.json` feature entry.
FEATURE_NAMES_KEY = "names"
FEATURE_SHAPE_KEY = "shape"
FEATURE_DTYPE_KEY = "dtype"
FEATURE_IS_DEPTH_KEY = "is_depth_map"

# ---------------------------------------------------------------------------
# The CTR-REC@v1 unit convention, mirrored (consumed via info.json name suffixes)
# ---------------------------------------------------------------------------

# The per-motor channel suffixes and their units. A single `observation.state`
# vector mixes three units, so an unlabelled plot misreads a torque as degrees
# (`FR-DAT-016`). `action` is position only by contract, so it only ever carries
# `.pos`; a `.vel`/`.torque` name on `action` is the FAIL_BLOCKING poison that
# `channels.following_error_pairs` refuses.
POSITION_SUFFIX = ".pos"
VELOCITY_SUFFIX = ".vel"
TORQUE_SUFFIX = ".torque"

POSITION_UNIT = "deg"
VELOCITY_UNIT = "deg/s"
TORQUE_UNIT = "Nm"

SUFFIX_UNITS = {
    POSITION_SUFFIX: POSITION_UNIT,
    VELOCITY_SUFFIX: VELOCITY_UNIT,
    TORQUE_SUFFIX: TORQUE_UNIT,
}

# The label shown when a channel matches no known suffix — never silently blank,
# so a missing unit is visible rather than mistaken for dimensionless.
UNKNOWN_UNIT = "?"

# A channel counts as "near" its limit at this fraction of the bound; at or past
# the bound it is "saturated" (`FR-DAT-013` near/saturation highlighting).
SATURATION_NEAR_FRACTION = 0.9
