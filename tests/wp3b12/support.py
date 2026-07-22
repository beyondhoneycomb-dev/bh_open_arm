"""Shared builders for the WP-3B-12 tests: frames from the synthetic dataset, real parquet fixtures.

The synthetic dataset (`contracts.fixtures.synthetic_dataset`) is this band's stand-in for
a real recording (`02b` §5.2 WP-3A-06). These helpers adapt its in-memory frames into the
`FrameSample` shape the quality metrics consume, and build the on-disk parquet fixtures the
crash path needs — a valid one and a footerless (crash-truncated) one.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from backend.recorder.quality.report import FrameSample
from contracts.fixtures.synthetic_dataset import SyntheticDataset


def frames_from_dataset(dataset: SyntheticDataset) -> list[FrameSample]:
    """Adapt a synthetic dataset's frames into the metric input shape.

    Args:
        dataset: A validated synthetic dataset.

    Returns:
        (list[FrameSample]) One sample per dataset frame, in order.
    """
    return [
        FrameSample(
            frame_index=frame.frame_index,
            timestamp=float(frame.meta["timestamp"]),
            action=dict(frame.action),
            observation_state=frame.observation_state,
        )
        for frame in dataset.frames
    ]


def write_valid_parquet(path: Path, rows: int = 8) -> Path:
    """Write a small, complete parquet whose footer and `PAR1` magic are present.

    Args:
        path: Destination path.
        rows: Row count.

    Returns:
        (Path) The written path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.table({"frame_index": list(range(rows)), "value": [float(i) for i in range(rows)]})
    pq.write_table(table, path)
    return path


def write_footerless_parquet(path: Path, rows: int = 8) -> Path:
    """Write a parquet then truncate its footer, simulating a crash mid-write.

    A complete parquet is written to a scratch sibling, and its first half — bytes without
    the trailing footer and `PAR1` magic — is written to `path`. That is the crash artefact
    `02b` §5.2 WP-3B-12 ⑤ requires the band to detect.

    Args:
        path: Destination path for the truncated file.
        rows: Row count of the complete file before truncation.

    Returns:
        (Path) The written, footerless path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    complete = path.with_suffix(".complete")
    write_valid_parquet(complete, rows)
    raw = complete.read_bytes()
    complete.unlink()
    path.write_bytes(raw[: len(raw) // 2])
    return path
