"""Materialize a raw capture source and a faithfully converted READY dataset.

WP-3C-06 is a cross-check between two artifacts, so a fixture is a *pair*: the raw
capture source (the pre-conversion output — a manifest and the CTR-CAP@v1
capture-timestamp sidecar per episode) and the converted LeRobot v3.0 dataset the
source became. Both are derived from the same `contracts.fixtures.synthetic_dataset`
frames, so a faithful pair agrees on every facet by construction and the fault
injectors (`faults.py`) are what break exactly one facet each.

The converted dataset is a genuine WP-3D-05 READY dataset — its `info.json`, packed
parquet, packed mp4s, depth TIFFs, episode metadata and stats sidecar are all
written so `ensure_training_ready` passes — plus the preserved capture_ts sidecar
under `meta/capture/`. The raw source records the original frame count and the same
capture instants, so the four capture-preservation checks pass on a faithful pair.
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

from backend.capture_interlock.constants import (
    CONVERTED_CAPTURE_SIDECAR_TEMPLATE,
    MANIFEST_EPISODE_INDEX_KEY,
    MANIFEST_FPS_KEY,
    MANIFEST_LENGTH_KEY,
    RAW_CAPTURE_TS_FILENAME,
    RAW_EPISODE_DIR_TEMPLATE,
    RAW_MANIFEST_FILENAME,
)
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
from contracts.capture.schema import sidecar_to_records
from contracts.fixtures.synthetic_dataset import (
    FIXTURE_FPS,
    FIXTURE_HEIGHT,
    FIXTURE_WIDTH,
    SyntheticDataset,
    build_synthetic_dataset,
)

_CODEBASE_VERSION = "v3.0"
_TASK = "synthetic-pick"
# The GOP the viewer bench pins random seek against; the packed video uses it so a
# demuxed frame count is exact.
_GOP_SIZE = "2"


@dataclass(frozen=True)
class Fixture:
    """Handles onto a materialized raw-source / converted-dataset pair.

    Attributes:
        raw_root: The raw capture source root.
        converted_root: The converted v3.0 dataset root.
        episodes: Episodes written.
        frames: Frames per episode (the original frame count N).
        fps: Dataset frame rate.
        rgb_keys: The packed-mp4 RGB feature keys.
        depth_key: The per-frame-TIFF depth key, or None when depth was omitted.
        stats_hash: The stats content hash recorded in info.json.
    """

    raw_root: Path
    converted_root: Path
    episodes: int
    frames: int
    fps: int
    rgb_keys: tuple[str, ...]
    depth_key: str | None
    stats_hash: str

    def data_parquet(self) -> Path:
        """The packed data parquet path."""
        return self.converted_root / DEFAULT_DATA_PATH_TEMPLATE.format(chunk_index=0, file_index=0)

    def episode_metadata_parquet(self) -> Path:
        """The packed episode-metadata parquet path."""
        return self.converted_root / "meta" / "episodes" / "chunk-000" / "file-000.parquet"

    def video_path(self, rgb_key: str, episode_index: int = 0) -> Path:
        """The mp4 path for an RGB camera's episode (one file per episode)."""
        return self.converted_root / DEFAULT_VIDEO_PATH_TEMPLATE.format(
            video_key=rgb_key, chunk_index=0, file_index=episode_index
        )

    def stats_path(self) -> Path:
        """The stats sidecar path."""
        return self.converted_root / STATS_RELATIVE_PATH

    def converted_capture_sidecar(self, episode_index: int) -> Path:
        """The converted capture_ts sidecar path for an episode."""
        return self.converted_root / CONVERTED_CAPTURE_SIDECAR_TEMPLATE.format(
            episode_index=episode_index
        )


def _rgb_frame(value: int, height: int, width: int) -> np.ndarray:
    """A solid deterministic RGB frame — cheap to encode for a correctness fixture."""
    return np.full((height, width, 3), value % 256, dtype=np.uint8)


def _depth_frame(base: int) -> np.ndarray:
    """A deterministic uint16 depth frame."""
    ramp = np.arange(FIXTURE_HEIGHT * FIXTURE_WIDTH, dtype=np.uint16).reshape(
        FIXTURE_HEIGHT, FIXTURE_WIDTH
    )
    return (ramp + base).astype(np.uint16)


def _metrics(values: np.ndarray) -> dict[str, list[float]]:
    """The ten per-dimension metrics of a `(frames, dim)` matrix (WP-3D-03 convention)."""
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


def _stats_table(
    datasets: list[SyntheticDataset], action_names: list[str]
) -> dict[str, dict[str, list[float]]]:
    """Compute the ten-metric stats table over observation.state and action."""
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
    return {OBSERVATION_STATE_KEY: _metrics(state), ACTION_KEY: _metrics(action)}


def _write_info(root: Path, features: dict, depth_key: str | None, stats_hash: str) -> None:
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


def _write_data_parquet(
    root: Path, datasets: list[SyntheticDataset], action_names: list[str]
) -> None:
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


def encode_episode_video(path: Path, frames: int, fps: int) -> None:
    """Encode one RGB camera episode's mp4 with exactly `frames` frames.

    One file per episode keeps the encoded frame count per-episode: demuxing the
    file yields that episode's frame count directly, which is what check ① compares
    to the original. Exposed (not private) so a fault injector can re-encode a single
    episode's file short without reaching into the packer.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("libx264", rate=fps)
        stream.width = FIXTURE_WIDTH
        stream.height = FIXTURE_HEIGHT
        stream.pix_fmt = "yuv420p"
        stream.options = {"g": _GOP_SIZE}
        for frame in range(frames):
            image = _rgb_frame(frame, FIXTURE_HEIGHT, FIXTURE_WIDTH)
            for packet in stream.encode(av.VideoFrame.from_ndarray(image, format="rgb24")):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


def _write_videos(root: Path, rgb_key: str, episodes: int, frames: int, fps: int) -> None:
    """Encode one mp4 per episode for an RGB camera (file_index == episode)."""
    for episode in range(episodes):
        path = root / DEFAULT_VIDEO_PATH_TEMPLATE.format(
            video_key=rgb_key, chunk_index=0, file_index=episode
        )
        encode_episode_video(path, frames, fps)


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
        # One mp4 per episode: file_index == episode, each video its own [0, (N-1)/fps].
        from_ts = 0.0
        to_ts = (frames - 1) / fps
        for key in rgb_keys:
            columns[f"videos/{key}/chunk_index"].append(0)
            columns[f"videos/{key}/file_index"].append(episode)
            columns[f"videos/{key}/from_timestamp"].append(from_ts)
            columns[f"videos/{key}/to_timestamp"].append(to_ts)

    path = root / "meta" / "episodes" / "chunk-000" / "file-000.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(columns), path)


def _write_converted_capture_sidecars(root: Path, datasets: list[SyntheticDataset]) -> None:
    """Write the preserved capture_ts sidecar for each episode under meta/capture."""
    for dataset in datasets:
        records = sidecar_to_records(dataset.sidecar)
        path = root / CONVERTED_CAPTURE_SIDECAR_TEMPLATE.format(
            episode_index=dataset.sidecar.episode_index
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")


def _write_raw_source(
    raw_root: Path, datasets: list[SyntheticDataset], frames: int, fps: int
) -> None:
    """Write the raw capture source: a manifest and capture_ts sidecar per episode."""
    for dataset in datasets:
        episode_index = dataset.sidecar.episode_index
        episode_dir = raw_root / RAW_EPISODE_DIR_TEMPLATE.format(episode_index=episode_index)
        episode_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            MANIFEST_EPISODE_INDEX_KEY: episode_index,
            MANIFEST_FPS_KEY: fps,
            MANIFEST_LENGTH_KEY: frames,
        }
        (episode_dir / RAW_MANIFEST_FILENAME).write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        records = sidecar_to_records(dataset.sidecar)
        (episode_dir / RAW_CAPTURE_TS_FILENAME).write_text(
            json.dumps(records, indent=2) + "\n", encoding="utf-8"
        )


def materialize(
    tmp_path: Path, episodes: int = 2, frames: int = 8, include_depth: bool = True
) -> Fixture:
    """Write a faithful raw-source / converted-READY-dataset pair.

    Args:
        tmp_path: The directory to write both artifacts under.
        episodes: Episodes to pack (>= 2 exercises the packed-segment offset).
        frames: Frames per episode — the original frame count N.
        include_depth: Whether to write the per-frame depth stream.

    Returns:
        (Fixture) Handles to the written raw source and converted dataset.
    """
    raw_root = Path(tmp_path) / "raw_capture"
    converted_root = Path(tmp_path) / "converted"

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

    _write_info(converted_root, datasets[0].info_features, depth_key, stats_hash)
    _write_stats(converted_root, table)
    _write_data_parquet(converted_root, datasets, action_names)
    for rgb_key in rgb_keys:
        _write_videos(converted_root, rgb_key, episodes, frames, FIXTURE_FPS)
    if depth_key is not None:
        _write_depth(converted_root, depth_key, episodes, frames)
    _write_episode_metadata(converted_root, rgb_keys, episodes, frames, FIXTURE_FPS)
    _write_converted_capture_sidecars(converted_root, datasets)

    _write_raw_source(raw_root, datasets, frames, FIXTURE_FPS)

    return Fixture(
        raw_root=raw_root,
        converted_root=converted_root,
        episodes=episodes,
        frames=frames,
        fps=FIXTURE_FPS,
        rgb_keys=tuple(rgb_keys),
        depth_key=depth_key,
        stats_hash=stats_hash,
    )
