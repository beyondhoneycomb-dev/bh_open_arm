"""Inject one integrity defect at a time into a materialized dataset.

Each injector takes a READY dataset (from `materialize`) and corrupts exactly one
property so the matching WP-3D-05 check must bite. The injectors are deliberately
surgical: an index-discontinuity injection leaves the parquet footers, the videos
and the stats untouched, so the acceptance test can prove the continuity check —
and only it — fired. A check that failed to bite here would be a check that would
pass a corrupt dataset through to a trainer.
"""

from __future__ import annotations

import json

import av
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from backend.dataset.viewer.constants import OBSERVATION_STATE_KEY
from tests.wp3d05.materialize import MaterializedDataset

# The GOP a re-encode must keep to match the original packing.
_GOP_SIZE = "2"
# The phantom camera an info.json-mismatch injection declares — a stream the
# chunk/file layout has no video for.
_PHANTOM_CAMERA_KEY = "observation.images.phantom_cam"


def inject_footerless_parquet(dataset: MaterializedDataset) -> None:
    """Truncate the data parquet so its footer and trailing magic are gone."""
    path = dataset.data_parquet()
    size = path.stat().st_size
    with path.open("r+b") as handle:
        handle.truncate(size // 2)


def inject_info_camera_mismatch(dataset: MaterializedDataset) -> None:
    """Declare a camera in info.json that the chunk/file layout has no video for."""
    path = dataset.info_path()
    info = json.loads(path.read_text(encoding="utf-8"))
    info["features"][_PHANTOM_CAMERA_KEY] = {
        "dtype": "uint8",
        "shape": ["height", "width", 3],
        "names": ["height", "width", "channels"],
        "is_depth_map": False,
    }
    path.write_text(json.dumps(info, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def inject_index_discontinuity(dataset: MaterializedDataset) -> None:
    """Shift one episode's dataset_from_index so the packed row ranges no longer tile."""
    path = dataset.episode_metadata_parquet()
    table = pq.read_table(path)
    column = table.column("dataset_from_index").to_pylist()
    target = 1 if len(column) > 1 else 0
    column[target] = column[target] + 1
    table = table.set_column(
        table.schema.get_field_index("dataset_from_index"),
        "dataset_from_index",
        pa.array(column, type=table.schema.field("dataset_from_index").type),
    )
    pq.write_table(table, path)


def inject_frame_count_mismatch(dataset: MaterializedDataset) -> None:
    """Re-encode one RGB mp4 with one frame fewer than the episodes declare."""
    path = dataset.video_path(dataset.rgb_keys[0])
    with av.open(str(path)) as source:
        stream = source.streams.video[0]
        height, width = stream.height, stream.width
    total_frames = dataset.episodes * dataset.frames
    with av.open(str(path), mode="w") as container:
        out = container.add_stream("libx264", rate=dataset.fps)
        out.width = width
        out.height = height
        out.pix_fmt = "yuv420p"
        out.options = {"g": _GOP_SIZE}
        for value in range(total_frames - 1):
            image = np.full((height, width, 3), value % 256, dtype=np.uint8)
            for packet in out.encode(av.VideoFrame.from_ndarray(image, format="rgb24")):
                container.mux(packet)
        for packet in out.encode():
            container.mux(packet)


def inject_dtype_mismatch(dataset: MaterializedDataset) -> None:
    """Rewrite observation.state as float64 while info.json still declares float32."""
    path = dataset.data_parquet()
    table = pq.read_table(path)
    index = table.schema.get_field_index(OBSERVATION_STATE_KEY)
    widened = table.column(OBSERVATION_STATE_KEY).cast(pa.list_(pa.float64()))
    table = table.set_column(index, OBSERVATION_STATE_KEY, widened)
    pq.write_table(table, path)


def inject_stats_hash_mismatch(dataset: MaterializedDataset) -> None:
    """Edit one value in meta/stats.json so it no longer hashes to the recorded value."""
    path = dataset.stats_path()
    table = json.loads(path.read_text(encoding="utf-8"))
    table[OBSERVATION_STATE_KEY]["mean"][0] += 1.0
    path.write_text(json.dumps(table, indent=2, sort_keys=True) + "\n", encoding="utf-8")
