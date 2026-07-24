"""Materialize the synthetic dataset fixture as a LeRobot v3.0 dataset on disk.

`02b` §5.2 WP-3A-06 ③: the fixtures alone must let a viewer test run without a
robot. This builder turns `build_synthetic_dataset` into an on-disk v3.0 dataset
the WP-3D-01 direct reader can open: `meta/info.json`, a packed
`data/chunk-000/file-000.parquet` holding several episodes, one packed mp4 per RGB
camera, per-frame depth TIFFs for one camera, and the `meta/episodes` metadata
that locates each episode's rows and video segment.

Two deliberate shapes exercise the reader's contract rather than its happy path:

- The episodes are packed into one data file and one mp4, so the reader must slice
  by `episode_index` and offset video by `from_timestamp` — a fixed-slot / one-file
  assumption would read episode 1 as episode 0.
- Each RGB frame is a solid luma encoding its *global* frame index, so a decoded
  frame identifies exactly which grid position it came from through lossy h264.
  This is test scaffolding, not the fixture's noise bytes, which would not survive
  mp4 encoding — the frame's *identity*, not its pixels, is what the scrub asserts.
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

# A frame's solid luma steps by this per global frame index, so a decoded frame's
# mean value identifies its grid position (mod 256) after lossy h264.
_LUMA_STEP = 15
_LUMA_MODULUS = 256

# The GOP the acceptance bench pins random seek against (`NFR-DAT-001`: g=2 favours
# random access); the materialized video is encoded with it.
_GOP_SIZE = "2"

_CODEBASE_VERSION = "v3.0"
_TASK = "synthetic-pick"


@dataclass(frozen=True)
class MaterializedDataset:
    """Handles onto a materialized on-disk dataset, for a test to assert against.

    Attributes:
        root: The dataset root directory.
        episodes: The number of episodes written.
        frames: The frames per episode.
        fps: The dataset frame rate.
        rgb_keys: The RGB `observation.images.*` feature keys (packed mp4).
        depth_key: The depth `observation.images.*_depth` key (per-frame TIFF).
    """

    root: Path
    episodes: int
    frames: int
    fps: int
    rgb_keys: tuple[str, ...]
    depth_key: str

    def expected_luma(self, episode_index: int, frame_index: int) -> int:
        """The solid luma a decoded RGB frame should carry at a grid position."""
        global_index = episode_index * self.frames + frame_index
        return (global_index * _LUMA_STEP) % _LUMA_MODULUS

    def expected_depth_value(self, episode_index: int, frame_index: int) -> int:
        """The base depth value the per-frame TIFF encodes at a grid position."""
        return episode_index * 1000 + frame_index * 100


def _rgb_frame(luma: int) -> np.ndarray:
    """A solid RGB frame at a given luma."""
    return np.full((FIXTURE_HEIGHT, FIXTURE_WIDTH, 3), luma, dtype=np.uint8)


def _depth_frame(base: int) -> np.ndarray:
    """A deterministic uint16 depth frame keyed by a base value."""
    ramp = np.arange(FIXTURE_HEIGHT * FIXTURE_WIDTH, dtype=np.uint16).reshape(
        FIXTURE_HEIGHT, FIXTURE_WIDTH
    )
    return (ramp + base).astype(np.uint16)


def _write_info(root: Path, features: dict, depth_key: str) -> None:
    """Write `meta/info.json`: the fixture feature set plus a depth stream."""
    info_features = dict(features)
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
    }
    path = root / "meta" / "info.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(info, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_data_parquet(root: Path, datasets: list, action_names: list[str]) -> None:
    """Write the packed `data/chunk-000/file-000.parquet` for all episodes."""
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


def _write_video(root: Path, rgb_key: str, spec: MaterializedDataset) -> None:
    """Encode one RGB camera's packed mp4 across every episode's frames."""
    path = root / DEFAULT_VIDEO_PATH_TEMPLATE.format(video_key=rgb_key, chunk_index=0, file_index=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    container = av.open(str(path), mode="w")
    stream = container.add_stream("libx264", rate=spec.fps)
    stream.width = FIXTURE_WIDTH
    stream.height = FIXTURE_HEIGHT
    stream.pix_fmt = "yuv420p"
    stream.options = {"g": _GOP_SIZE}
    for episode in range(spec.episodes):
        for frame in range(spec.frames):
            image = _rgb_frame(spec.expected_luma(episode, frame))
            for packet in stream.encode(av.VideoFrame.from_ndarray(image, format="rgb24")):
                container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()


def _write_depth(root: Path, depth_key: str, spec: MaterializedDataset) -> None:
    """Write per-frame depth TIFFs for the depth camera, one dir per episode."""
    for episode in range(spec.episodes):
        for frame in range(spec.frames):
            image = _depth_frame(spec.expected_depth_value(episode, frame))
            path = (
                root / "images" / depth_key / f"episode-{episode:06d}" / f"frame-{frame:06d}.tiff"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(image).save(path)


def _write_episode_metadata(root: Path, rgb_keys: list[str], spec: MaterializedDataset) -> None:
    """Write `meta/episodes/chunk-000/file-000.parquet` locating each episode."""
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

    for episode in range(spec.episodes):
        columns["episode_index"].append(episode)
        columns["length"].append(spec.frames)
        columns["tasks"].append([_TASK])
        columns["dataset_from_index"].append(episode * spec.frames)
        columns["dataset_to_index"].append((episode + 1) * spec.frames)
        columns["data/chunk_index"].append(0)
        columns["data/file_index"].append(0)
        from_ts = episode * spec.frames / spec.fps
        to_ts = ((episode + 1) * spec.frames - 1) / spec.fps
        for key in rgb_keys:
            columns[f"videos/{key}/chunk_index"].append(0)
            columns[f"videos/{key}/file_index"].append(0)
            columns[f"videos/{key}/from_timestamp"].append(from_ts)
            columns[f"videos/{key}/to_timestamp"].append(to_ts)

    path = root / "meta" / "episodes" / "chunk-000" / "file-000.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(columns), path)


def materialize(root: Path, episodes: int = 2, frames: int = 8) -> MaterializedDataset:
    """Write a packed, multi-episode v3.0 dataset from the synthetic fixture.

    Args:
        root: The directory to write the dataset into.
        episodes: The number of episodes to pack (>= 2 exercises segment offset).
        frames: The frames per episode.

    Returns:
        (MaterializedDataset) Handles to the written dataset for a test to assert.
    """
    datasets = [
        build_synthetic_dataset(episode_index=episode, frame_count=frames)
        for episode in range(episodes)
    ]
    config = datasets[0].config
    rgb_keys = [slot.image_key() for slot in config.camera_slots]
    depth_key = config.camera_slots[0].depth_key()
    action_names = list(datasets[0].info_features[ACTION_KEY][FEATURE_NAMES_KEY])

    spec = MaterializedDataset(
        root=Path(root),
        episodes=episodes,
        frames=frames,
        fps=FIXTURE_FPS,
        rgb_keys=tuple(rgb_keys),
        depth_key=depth_key,
    )

    _write_info(spec.root, datasets[0].info_features, depth_key)
    _write_data_parquet(spec.root, datasets, action_names)
    for rgb_key in rgb_keys:
        _write_video(spec.root, rgb_key, spec)
    _write_depth(spec.root, depth_key, spec)
    _write_episode_metadata(spec.root, rgb_keys, spec)
    return spec
