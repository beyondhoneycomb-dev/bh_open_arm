"""Inject one capture-preservation defect at a time into a materialized pair.

Each injector takes a faithful raw-source / converted-dataset pair and corrupts
exactly one facet so the matching WP-3C-06 check must bite. The injectors are
surgical: a frame-count short leaves the parquet rows, the declared video span and
the capture_ts untouched, so an acceptance test can prove that check — and only it —
fired. A check that failed to bite here would be a check that licenses an
irreversible delete of a source the conversion did not preserve.

The last injector is different in kind: it corrupts the converted dataset so
WP-3D-05 rules it INVALID while leaving all four capture-preservation checks
passing, which proves the READY gate and the capture layer are independent — a
delete is refused on either one alone.
"""

from __future__ import annotations

import json

import pyarrow as pa
import pyarrow.parquet as pq

from backend.dataset.viewer.constants import (
    EPISODE_INDEX_COLUMN,
    FRAME_INDEX_COLUMN,
    OBSERVATION_STATE_KEY,
)
from contracts.prim import CAPTURE_TS_COLUMN_SUFFIX
from tests.wp3c06.materialize import Fixture, encode_episode_video


def inject_frame_count_short(fixture: Fixture) -> None:
    """Re-encode episode 0's RGB mp4 with one frame fewer than captured (①).

    The demuxed converted frame count for episode 0 then falls short of the raw
    source's frame count while the parquet, the declared span and the capture_ts
    stay intact — so only check ① bites, and only for episode 0.
    """
    path = fixture.video_path(fixture.rgb_keys[0], episode_index=0)
    encode_episode_video(path, fixture.frames - 1, fixture.fps)


def inject_video_length_off(fixture: Fixture) -> None:
    """Stretch one episode's declared video span past the episode length (②).

    Bumping `to_timestamp` makes the declared frame span exceed the original frame
    count without touching the encoded bytes, the rows, or the capture_ts.
    """
    path = fixture.episode_metadata_parquet()
    table = pq.read_table(path)
    column_name = f"videos/{fixture.rgb_keys[0]}/to_timestamp"
    values = table.column(column_name).to_pylist()
    values[0] = values[0] + 2.0 / fixture.fps
    table = table.set_column(
        table.schema.get_field_index(column_name),
        column_name,
        pa.array(values, type=table.schema.field(column_name).type),
    )
    pq.write_table(table, path)


def inject_row_count_off(fixture: Fixture) -> None:
    """Drop one data-parquet row from episode 0 so its row count falls short (③).

    The encoded video, declared span and capture_ts are untouched; only the number
    of state/action rows for the episode changes.
    """
    path = fixture.data_parquet()
    table = pq.read_table(path)
    episodes = table.column(EPISODE_INDEX_COLUMN).to_pylist()
    frames = table.column(FRAME_INDEX_COLUMN).to_pylist()
    drop_row = next(
        row for row, (ep, fr) in enumerate(zip(episodes, frames, strict=True)) if ep == 0
    )
    keep = [row for row in range(table.num_rows) if row != drop_row]
    pq.write_table(table.take(pa.array(keep)), path)


def inject_capture_ts_reordered(fixture: Fixture) -> None:
    """Swap two capture instants in episode 0's converted capture_ts sidecar (④).

    Exchanging the first two frames' capture_ts for one slot makes the converted
    sequence non-monotonic and changes its content hash, so it no longer matches the
    raw source — capture time was not preserved. Frame indices are left in place, so
    the sidecar still parses; the values are what diverge.
    """
    path = fixture.converted_capture_sidecar(0)
    records = json.loads(path.read_text(encoding="utf-8"))
    slot_column = next(key for key in records[0] if key.endswith(CAPTURE_TS_COLUMN_SUFFIX))
    records[0][slot_column], records[1][slot_column] = (
        records[1][slot_column],
        records[0][slot_column],
    )
    path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")


def inject_ready_invalid(fixture: Fixture) -> None:
    """Corrupt meta/stats.json so WP-3D-05 rules the dataset INVALID (READY gate).

    The stats table no longer hashes to the recorded value, so `ensure_training_ready`
    raises — while the four capture-preservation checks, which never read stats, all
    still pass. This isolates the READY gate from the capture layer.
    """
    path = fixture.stats_path()
    table = json.loads(path.read_text(encoding="utf-8"))
    table[OBSERVATION_STATE_KEY]["mean"][0] += 1.0
    path.write_text(json.dumps(table, indent=2, sort_keys=True) + "\n", encoding="utf-8")
