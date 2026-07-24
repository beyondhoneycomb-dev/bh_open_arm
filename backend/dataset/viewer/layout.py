"""Dataset layout resolution: `meta/info.json` + episode metadata -> file paths.

This is the direct reader's map of a LeRobot v3.0 dataset on disk. It reads
`meta/info.json` for the feature set, fps and path templates, and the packed
`meta/episodes/*` metadata to locate one episode: which data parquet holds its
rows, and for each video stream which mp4 and which `[from_timestamp,
to_timestamp]` segment inside it. No LeRobot import is involved — the layout is a
storage convention consumed as data (`WP-3D-01` 참조근거, `06` §5.6).

Row location is by the `episode_index` column of the data table rather than the
global `dataset_from_index`/`dataset_to_index` bookkeeping, so a packed file
holding several episodes is sliced correctly without reconstructing the global-to
-local index mapping.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from backend.dataset.viewer.channels import CameraStream, camera_streams
from backend.dataset.viewer.constants import (
    DEFAULT_DATA_PATH_TEMPLATE,
    DEFAULT_VIDEO_PATH_TEMPLATE,
    EPISODE_INDEX_COLUMN,
    EPISODE_LENGTH_COLUMN,
    EPISODE_TASKS_COLUMN,
    INFO_DATA_PATH_KEY,
    INFO_FEATURES_KEY,
    INFO_FPS_KEY,
    INFO_RELATIVE_PATH,
    INFO_VIDEO_PATH_KEY,
    video_chunk_index_column,
    video_file_index_column,
    video_from_timestamp_column,
    video_to_timestamp_column,
)


class DatasetLayoutError(ValueError):
    """Raised when a dataset directory cannot be read as a LeRobot v3.0 dataset.

    Covers a missing/corrupt `info.json`, an episode index absent from the
    metadata, and an unreadable (e.g. footerless/crash-truncated) metadata
    parquet. The viewer never fabricates a fallback for these — a corrupt file
    surfaces as an error, not a silent empty episode.
    """


def _scalar(value: Any) -> Any:
    """Return a single value from a metadata cell that may be wrapped in a list.

    Episode-metadata columns such as `dataset_from_index` are written as a
    one-element list per row; index columns are plain scalars. This collapses the
    list form without disturbing the scalar form.
    """
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value[0] if value else None
    return value


@dataclass(frozen=True)
class VideoSegment:
    """One video stream's mp4 file and the episode's segment within it.

    A packed mp4 holds several episodes back to back; `from_timestamp` is where
    this episode begins in the file, so a grid frame `i` is at container time
    `from_timestamp + i / fps` (`06` §5, the v3.0 read path).

    Attributes:
        image_key: The stream's `observation.images.*` feature key.
        file: Absolute path to the mp4.
        from_timestamp: The episode's start second inside the packed mp4.
        to_timestamp: The episode's end second inside the packed mp4.
    """

    image_key: str
    file: Path
    from_timestamp: float
    to_timestamp: float


@dataclass(frozen=True)
class EpisodeLocation:
    """Everything needed to read one episode: its data file and video segments.

    Attributes:
        episode_index: The episode this location resolves.
        length: The episode's frame count from the metadata (`0` when unknown).
        tasks: The task strings attached to the episode.
        data_file: Absolute path to the packed parquet holding the episode's rows.
        video_segments: Per-image-key video segments, for streams stored as mp4.
            Streams stored as per-frame images carry no segment here.
    """

    episode_index: int
    length: int
    tasks: tuple[str, ...]
    data_file: Path
    video_segments: dict[str, VideoSegment]


class DatasetLayout:
    """A LeRobot v3.0 dataset on disk, read directly for the episode viewer.

    Ownership: this object holds no file handles; it reads `info.json` and the
    episode metadata eagerly at construction and resolves per-episode file paths
    on demand. It is safe to construct once and query per episode.
    """

    def __init__(self, root: Path) -> None:
        """Read `info.json` and the episode metadata for a dataset directory.

        Args:
            root: The dataset root (the directory holding `meta/`, `data/`, `videos/`).

        Raises:
            DatasetLayoutError: If `info.json` is missing or malformed.
        """
        self.root = Path(root)
        self.info = self._load_info()
        self.features: Mapping[str, Any] = self.info[INFO_FEATURES_KEY]
        self.fps = int(self.info[INFO_FPS_KEY])
        self.data_path_template = str(
            self.info.get(INFO_DATA_PATH_KEY) or DEFAULT_DATA_PATH_TEMPLATE
        )
        self.video_path_template = str(
            self.info.get(INFO_VIDEO_PATH_KEY) or DEFAULT_VIDEO_PATH_TEMPLATE
        )
        self.episodes = self._load_episode_metadata()

    def _load_info(self) -> dict[str, Any]:
        """Read and validate `meta/info.json`."""
        path = self.root / INFO_RELATIVE_PATH
        if not path.is_file():
            raise DatasetLayoutError(f"{path} is missing; not a LeRobot dataset directory")
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as bad:
            raise DatasetLayoutError(f"{path} is not valid JSON: {bad}") from bad
        if (
            not isinstance(info, Mapping)
            or INFO_FEATURES_KEY not in info
            or INFO_FPS_KEY not in info
        ):
            raise DatasetLayoutError(
                f"{path} lacks required {INFO_FEATURES_KEY!r}/{INFO_FPS_KEY!r}"
            )
        if int(info[INFO_FPS_KEY]) <= 0:
            raise DatasetLayoutError(f"{path} declares a non-positive fps {info[INFO_FPS_KEY]!r}")
        return dict(info)

    def _load_episode_metadata(self) -> dict[int, dict[str, Any]]:
        """Read every `meta/episodes/*` parquet into an episode-index-keyed map.

        Returns an empty map when no metadata directory exists; `locate` then
        falls back to the default single-file layout.

        Raises:
            DatasetLayoutError: If a metadata parquet exists but cannot be read.
        """
        meta_dir = self.root / "meta" / "episodes"
        if not meta_dir.is_dir():
            return {}
        episodes: dict[int, dict[str, Any]] = {}
        for parquet in sorted(meta_dir.rglob("file-*.parquet")):
            try:
                table = pq.read_table(parquet)
            except Exception as bad:  # noqa: BLE001 — any pyarrow read failure is a corrupt-file signal
                raise DatasetLayoutError(
                    f"episode metadata {parquet} is unreadable: {bad}"
                ) from bad
            rows = table.to_pylist()
            for row in rows:
                index = _scalar(row.get(EPISODE_INDEX_COLUMN))
                if index is not None:
                    episodes[int(index)] = row
        return episodes

    def episode_indices(self) -> tuple[int, ...]:
        """Return the episode indices the metadata declares, ascending."""
        return tuple(sorted(self.episodes))

    def camera_streams(self) -> tuple[CameraStream, ...]:
        """Return the configured camera streams from `info.json` (RGB and depth)."""
        return camera_streams(self.features)

    def _resolve(self, template: str, **fields: Any) -> Path:
        """Resolve a path template against the dataset root."""
        return self.root / template.format(**fields)

    def _video_segment(self, image_key: str, row: Mapping[str, Any], length: int) -> VideoSegment:
        """Build a stream's video segment from an episode metadata row.

        Falls back to the default chunk/file (0/0) and a `[0, length/fps]` segment
        when the metadata omits the per-key columns, which is the single-episode
        -per-file case.
        """
        chunk = _scalar(row.get(video_chunk_index_column(image_key), 0)) or 0
        file = _scalar(row.get(video_file_index_column(image_key), 0)) or 0
        from_ts = _scalar(row.get(video_from_timestamp_column(image_key), 0.0)) or 0.0
        default_to = length / self.fps if length else 0.0
        to_ts = _scalar(row.get(video_to_timestamp_column(image_key), default_to))
        if to_ts is None:
            to_ts = default_to
        path = self._resolve(
            self.video_path_template,
            video_key=image_key,
            chunk_index=int(chunk),
            file_index=int(file),
        )
        return VideoSegment(
            image_key=image_key, file=path, from_timestamp=float(from_ts), to_timestamp=float(to_ts)
        )

    def locate(self, episode_index: int) -> EpisodeLocation:
        """Resolve the data file and video segments for one episode.

        Args:
            episode_index: The zero-based episode to locate.

        Returns:
            (EpisodeLocation) The episode's data parquet and per-stream video
                segments; streams stored as per-frame images carry no segment.

        Raises:
            DatasetLayoutError: If the episode index is not present in metadata
                that does exist.
        """
        row = self.episodes.get(episode_index)
        if row is None and self.episodes:
            raise DatasetLayoutError(
                f"episode {episode_index} is not in the dataset metadata "
                f"(have {self.episode_indices()})"
            )
        row = row or {}

        data_chunk = _scalar(row.get("data/chunk_index", 0)) or 0
        data_file = _scalar(row.get("data/file_index", 0)) or 0
        data_path = self._resolve(
            self.data_path_template, chunk_index=int(data_chunk), file_index=int(data_file)
        )

        length = int(_scalar(row.get(EPISODE_LENGTH_COLUMN, 0)) or 0)
        tasks_cell = row.get(EPISODE_TASKS_COLUMN, [])
        tasks = (
            tuple(str(task) for task in tasks_cell)
            if isinstance(tasks_cell, Sequence) and not isinstance(tasks_cell, str)
            else ()
        )

        segments: dict[str, VideoSegment] = {}
        for stream in self.camera_streams():
            segment = self._video_segment(stream.image_key, row, length)
            if segment.file.is_file():
                segments[stream.image_key] = segment

        return EpisodeLocation(
            episode_index=episode_index,
            length=length,
            tasks=tasks,
            data_file=data_path,
            video_segments=segments,
        )
