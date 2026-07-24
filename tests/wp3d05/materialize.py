"""Materialize the synthetic fixture as a v3.0 dataset the integrity verifier reads.

This writes the on-disk shape WP-3D-05 checks: `meta/info.json` (carrying the
recorded stats hash), a packed `data/chunk-000/file-000.parquet`, one packed mp4
per RGB camera, per-frame depth TIFFs, the `meta/episodes` locator, and
`meta/stats.json`. The stats table is computed from the frames and hashed with the
committed WP-3D-03 routine, so a valid dataset's sidecar and its recorded hash
agree by construction — the fault injectors (see `faults.py`) are what break them.

The materializer builds a genuinely READY dataset; the tests inject one defect at a
time into a copy and assert the matching check bites. The video resolution is a
materializer parameter because `info.json` pins image shape symbolically
(`["height", "width", 3]`), so a larger video for the throughput fixture stays
consistent with the metadata.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import av
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from PIL import Image

from backend.dataset.integrity.constants import INFO_STATS_HASH_KEY, STATS_RELATIVE_PATH
from backend.dataset.stats.constants import QUANTILE_KEYS, QUANTILE_LEVELS
from backend.dataset.stats.hashing import stats_content_hash
from backend.dataset.viewer.constants import (
    ACTION_KEY,
    DEFAULT_DATA_PATH_TEMPLATE,
    DEFAULT_VIDEO_PATH_TEMPLATE,
    FEATURE_IS_DEPTH_KEY,
    FEATURE_NAMES_KEY,
    OBSERVATION_STATE_KEY,
)
from contracts.fixtures.synthetic_dataset import (
    FIXTURE_FPS,
    FIXTURE_HEIGHT,
    FIXTURE_WIDTH,
    build_synthetic_dataset,
)

_CODEBASE_VERSION = "v3.0"
_TASK = "synthetic-pick"
# The GOP the viewer bench pins random seek against; the packed video uses it.
_GOP_SIZE = "2"


@dataclass(frozen=True)
class MaterializedDataset:
    """Handles onto a materialized on-disk dataset for a test to assert against.

    Attributes:
        root: The dataset root directory.
        episodes: Episodes written.
        frames: Frames per episode.
        fps: Dataset frame rate.
        rgb_keys: The packed-mp4 RGB feature keys.
        depth_key: The per-frame-TIFF depth key, or None when depth was omitted.
        stats_hash: The stats content hash recorded in info.json.
    """

    root: Path
    episodes: int
    frames: int
    fps: int
    rgb_keys: tuple[str, ...]
    depth_key: str | None
    stats_hash: str

    def data_parquet(self) -> Path:
        """The packed data parquet path."""
        return self.root / DEFAULT_DATA_PATH_TEMPLATE.format(chunk_index=0, file_index=0)

    def episode_metadata_parquet(self) -> Path:
        """The packed episode-metadata parquet path."""
        return self.root / "meta" / "episodes" / "chunk-000" / "file-000.parquet"

    def video_path(self, rgb_key: str) -> Path:
        """The packed mp4 path for an RGB camera."""
        return self.root / DEFAULT_VIDEO_PATH_TEMPLATE.format(
            video_key=rgb_key, chunk_index=0, file_index=0
        )

    def info_path(self) -> Path:
        """The info.json path."""
        return self.root / "meta" / "info.json"

    def stats_path(self) -> Path:
        """The stats sidecar path."""
        return self.root / STATS_RELATIVE_PATH


def _rgb_frame(value: int, height: int, width: int, noise: bool) -> np.ndarray:
    """An RGB frame; solid for a small fixture, random noise for a byte-heavy one.

    Solid frames encode to almost nothing, which is fine for a correctness fixture
    but useless for a throughput fixture: the regression bound is byte-relative, so
    the throughput test needs frames that do not compress away.
    """
    if noise:
        return np.random.default_rng(value + 1).integers(0, 256, (height, width, 3), dtype=np.uint8)
    return np.full((height, width, 3), value % 256, dtype=np.uint8)


def _depth_frame(base: int) -> np.ndarray:
    """A deterministic uint16 depth frame."""
    ramp = np.arange(FIXTURE_HEIGHT * FIXTURE_WIDTH, dtype=np.uint16).reshape(
        FIXTURE_HEIGHT, FIXTURE_WIDTH
    )
    return (ramp + base).astype(np.uint16)


def _stats_table(datasets: list, action_names: list[str]) -> dict[str, dict[str, list[float]]]:
    """Compute a real ten-metric stats table over the observation.state and action.

    The metric set matches the WP-3D-03 convention; the values are genuine
    per-dimension statistics of the materialized frames. The table is what both
    `meta/stats.json` and the recorded hash are derived from, so they agree.
    """
    state = np.array(
        [list(frame.observation_state) for dataset in datasets for frame in dataset.frames],
        dtype=np.float64,
    )
    action = np.array(
        [
            [frame.action[name] for name in action_names]
            for dataset in datasets
            for frame in dataset.frames
        ],
        dtype=np.float64,
    )
    return {
        OBSERVATION_STATE_KEY: _metrics(state),
        ACTION_KEY: _metrics(action),
    }


def _metrics(values: np.ndarray) -> dict[str, list[float]]:
    """The ten per-dimension metrics of a `(frames, dim)` matrix."""
    table: dict[str, list[float]] = {
        "mean": values.mean(axis=0).tolist(),
        "std": values.std(axis=0).tolist(),
        "min": values.min(axis=0).tolist(),
        "max": values.max(axis=0).tolist(),
        "count": [float(values.shape[0])],
    }
    for key, level in zip(QUANTILE_KEYS, QUANTILE_LEVELS, strict=True):
        table[key] = np.quantile(values, level, axis=0).tolist()
    return table


def _write_info(
    root: Path,
    features: dict,
    depth_key: str | None,
    stats_hash: str,
) -> None:
    """Write meta/info.json: the fixture feature set, a depth stream, the stats hash."""
    info_features = dict(features)
    if depth_key is not None:
        info_features[depth_key] = {
            "dtype": "uint16",
            "shape": [FIXTURE_HEIGHT, FIXTURE_WIDTH, 1],
            FEATURE_NAMES_KEY: ["height", "width", "channels"],
            FEATURE_IS_DEPTH_KEY: True,
        }
    info = {
        "codebase_version": _CODEBASE_VERSION,
        "fps": FIXTURE_FPS,
        "robot_type": "openarm_bimanual",
        "data_path": DEFAULT_DATA_PATH_TEMPLATE,
        "video_path": DEFAULT_VIDEO_PATH_TEMPLATE,
        "features": info_features,
        INFO_STATS_HASH_KEY: stats_hash,
    }
    path = root / "meta" / "info.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(info, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_stats(root: Path, table: dict) -> None:
    """Write meta/stats.json."""
    path = root / STATS_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(table, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_data_parquet(root: Path, datasets: list, action_names: list[str]) -> None:
    """Write the packed data parquet for all episodes."""
    state: list[list[float]] = []
    action: list[list[float]] = []
    frame_index: list[int] = []
    episode_index: list[int] = []
    index: list[int] = []
    task_index: list[int] = []
    global_index = 0
    for dataset in datasets:
        for frame in dataset.frames:
            state.append([float(v) for v in frame.observation_state])
            action.append([float(frame.action[name]) for name in action_names])
            frame_index.append(int(frame.frame_index))
            episode_index.append(int(frame.meta["episode_index"]))
            index.append(global_index)
            task_index.append(int(frame.meta["task_index"]))
            global_index += 1

    table = pa.table(
        {
            OBSERVATION_STATE_KEY: pa.array(state, type=pa.list_(pa.float32())),
            ACTION_KEY: pa.array(action, type=pa.list_(pa.float32())),
            "timestamp": pa.array([f / FIXTURE_FPS for f in frame_index], type=pa.float32()),
            "frame_index": pa.array(frame_index, type=pa.int64()),
            "episode_index": pa.array(episode_index, type=pa.int64()),
            "index": pa.array(index, type=pa.int64()),
            "task_index": pa.array(task_index, type=pa.int64()),
        }
    )
    path = root / DEFAULT_DATA_PATH_TEMPLATE.format(chunk_index=0, file_index=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)


def _write_video(
    root: Path,
    rgb_key: str,
    episodes: int,
    frames: int,
    fps: int,
    size: tuple[int, int],
    noise: bool,
) -> None:
    """Encode one RGB camera's packed mp4 across every episode's frames."""
    height, width = size
    path = root / DEFAULT_VIDEO_PATH_TEMPLATE.format(video_key=rgb_key, chunk_index=0, file_index=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("libx264", rate=fps)
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"
        stream.options = {"g": _GOP_SIZE}
        counter = 0
        for _ in range(episodes):
            for _ in range(frames):
                image = _rgb_frame(counter, height, width, noise)
                for packet in stream.encode(av.VideoFrame.from_ndarray(image, format="rgb24")):
                    container.mux(packet)
                counter += 1
        for packet in stream.encode():
            container.mux(packet)


def _write_depth(root: Path, depth_key: str, episodes: int, frames: int) -> None:
    """Write per-frame depth TIFFs, one directory per episode."""
    for episode in range(episodes):
        for frame in range(frames):
            image = _depth_frame(episode * 1000 + frame * 100)
            path = (
                root / "images" / depth_key / f"episode-{episode:06d}" / f"frame-{frame:06d}.tiff"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(image).save(path)


def _write_episode_metadata(
    root: Path, rgb_keys: list[str], episodes: int, frames: int, fps: int
) -> None:
    """Write meta/episodes locating each episode's rows and video segment."""
    columns: dict[str, list] = {
        "episode_index": [],
        "length": [],
        "tasks": [],
        "dataset_from_index": [],
        "dataset_to_index": [],
        "data/chunk_index": [],
        "data/file_index": [],
    }
    for key in rgb_keys:
        columns[f"videos/{key}/chunk_index"] = []
        columns[f"videos/{key}/file_index"] = []
        columns[f"videos/{key}/from_timestamp"] = []
        columns[f"videos/{key}/to_timestamp"] = []

    for episode in range(episodes):
        columns["episode_index"].append(episode)
        columns["length"].append(frames)
        columns["tasks"].append([_TASK])
        columns["dataset_from_index"].append(episode * frames)
        columns["dataset_to_index"].append((episode + 1) * frames)
        columns["data/chunk_index"].append(0)
        columns["data/file_index"].append(0)
        from_ts = episode * frames / fps
        to_ts = ((episode + 1) * frames - 1) / fps
        for key in rgb_keys:
            columns[f"videos/{key}/chunk_index"].append(0)
            columns[f"videos/{key}/file_index"].append(0)
            columns[f"videos/{key}/from_timestamp"].append(from_ts)
            columns[f"videos/{key}/to_timestamp"].append(to_ts)

    path = root / "meta" / "episodes" / "chunk-000" / "file-000.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(columns), path)


def materialize(
    root: Path,
    episodes: int = 2,
    frames: int = 8,
    include_depth: bool = True,
    video_size: tuple[int, int] | None = None,
    noise_video: bool = False,
) -> MaterializedDataset:
    """Write a READY packed multi-episode v3.0 dataset from the synthetic fixture.

    Args:
        root: The directory to write into.
        episodes: Episodes to pack (>= 2 exercises the segment offset).
        frames: Frames per episode.
        include_depth: Whether to write the per-frame depth stream.
        video_size: `(height, width)` for the encoded mp4; defaults to fixture size.
        noise_video: Encode random frames (byte-heavy) for a throughput fixture.

    Returns:
        (MaterializedDataset) Handles to the written dataset.
    """
    root = Path(root)
    size = video_size if video_size is not None else (FIXTURE_HEIGHT, FIXTURE_WIDTH)
    datasets = [
        build_synthetic_dataset(episode_index=episode, frame_count=frames)
        for episode in range(episodes)
    ]
    config = datasets[0].config
    rgb_keys = [slot.image_key() for slot in config.camera_slots]
    depth_key = config.camera_slots[0].depth_key() if include_depth else None
    action_names = list(datasets[0].info_features[ACTION_KEY][FEATURE_NAMES_KEY])

    table = _stats_table(datasets, action_names)
    stats_hash = stats_content_hash(table)

    _write_info(root, datasets[0].info_features, depth_key, stats_hash)
    _write_stats(root, table)
    _write_data_parquet(root, datasets, action_names)
    for rgb_key in rgb_keys:
        _write_video(root, rgb_key, episodes, frames, FIXTURE_FPS, size, noise_video)
    if depth_key is not None:
        _write_depth(root, depth_key, episodes, frames)
    _write_episode_metadata(root, rgb_keys, episodes, frames, FIXTURE_FPS)

    return MaterializedDataset(
        root=root,
        episodes=episodes,
        frames=frames,
        fps=FIXTURE_FPS,
        rgb_keys=tuple(rgb_keys),
        depth_key=depth_key,
        stats_hash=stats_hash,
    )
