"""Fault injection for the crash/resume drill (WP-3C-07 phase-1, AI-offline).

`02b` §7 WP-3C-07: SIGKILL, disk-full and network-cut are injected, and each leaves a
different incomplete-dataset artefact the recovery means must repair. The plan fixes
phase-1 as an `AI-offline` simulation, so each injector produces the on-disk *state*
its fault causes — but the SIGKILL is not simulated at the file level: it spawns a real
subprocess writing a real parquet and kills it before the footer, so the footerless
artefact is the product of an actual kill (`faults.inject_sigkill`).

The three faults map onto the three recovery means:

- SIGKILL     -> a footerless packed parquet   -> detect + isolate (means: truncate)
- DISK_FULL   -> a partial trailing episode with stale `meta/episodes`
                                                -> means: truncate + rebuild meta
- NETWORK_CUT -> a video segment no episode references
                                                -> means: drop unmatched video
"""

from __future__ import annotations

import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from backend.crash_recovery.constants import (
    EPISODE_INDEX_COLUMN,
    FRAME_INDEX_COLUMN,
    INDEX_COLUMN,
    VIDEO_SEGMENT_TEMPLATE,
)
from backend.crash_recovery.layout import data_parquets

# The worker module the SIGKILL injector spawns, and the bounded wait for its
# readiness sentinel. The wait is a ceiling on process start + one row-group write, not
# a pacing sleep: the kill fires the instant the sentinel appears.
_WORKER_MODULE = "backend.crash_recovery.crash_worker"
_SENTINEL_SUFFIX = ".ready"
_READY_TIMEOUT_SECONDS = 30.0
_POLL_INTERVAL_SECONDS = 0.01

# Bytes written to a fabricated video segment for the network-cut fault. The content
# is irrelevant — the means keys off whether any episode *references* the file, not its
# decodability — so a short marker stands in for an encoded segment.
_STUB_VIDEO_BYTES = b"\x00stub-mp4-segment\x00"


class FaultKind(StrEnum):
    """The three crash faults phase-1 injects."""

    SIGKILL = "sigkill"
    DISK_FULL = "disk-full"
    NETWORK_CUT = "network-cut"


@dataclass(frozen=True)
class InjectedFault:
    """What a fault injection left on disk, for the recovery step to act on.

    Attributes:
        kind: Which fault was injected.
        description: A human-readable account of the artefact.
        footerless_parquet: The footerless packed parquet a SIGKILL left, else None.
        partial_episode_index: The index of the partial trailing episode a disk-full
            left in the packed data, else None.
        stale_meta: Whether `meta/episodes` was left not describing the partial episode
            (a disk-full leaves the metadata update uncommitted).
        unmatched_video: A video segment no episode references, from a network cut, else
            None.
    """

    kind: FaultKind
    description: str
    footerless_parquet: Path | None
    partial_episode_index: int | None
    stale_meta: bool
    unmatched_video: Path | None


def inject_sigkill(target_parquet: Path, rows: int) -> InjectedFault:
    """Produce a genuinely footerless parquet by SIGKILLing a real writer mid-write.

    A subprocess writes one row group to `target_parquet`, signals readiness, and
    blocks; this function kills it with SIGKILL before it can write the footer. The
    file left behind carries data but no trailing `PAR1` magic — a real crash artefact,
    not a hand-truncated one.

    Args:
        target_parquet: Where the footerless parquet is written (typically the in-flight
            episode's data file).
        rows: How many rows the row group holds.

    Returns:
        (InjectedFault) Describing the footerless parquet.

    Raises:
        RuntimeError: When the writer never signals readiness within the timeout, so no
            footerless artefact was produced (a failed injection, never a silent pass).
    """
    sentinel = target_parquet.with_suffix(target_parquet.suffix + _SENTINEL_SUFFIX)
    if sentinel.exists():
        sentinel.unlink()

    process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell, our own module
        [sys.executable, "-m", _WORKER_MODULE, str(target_parquet), str(sentinel), str(rows)]
    )
    try:
        _wait_for_sentinel(sentinel, process)
        process.send_signal(signal.SIGKILL)
    finally:
        process.wait()
        if sentinel.exists():
            sentinel.unlink()

    if not target_parquet.is_file():
        raise RuntimeError(
            f"SIGKILL injection produced no parquet at {target_parquet}; injection failed"
        )
    return InjectedFault(
        kind=FaultKind.SIGKILL,
        description=f"writer SIGKILLed after a row group, before the footer, at {target_parquet}",
        footerless_parquet=target_parquet,
        partial_episode_index=None,
        stale_meta=False,
        unmatched_video=None,
    )


def _wait_for_sentinel(sentinel: Path, process: subprocess.Popen[bytes]) -> None:
    """Block until the worker signals readiness, or fail if it dies or times out.

    Args:
        sentinel: The readiness file the worker creates once its row group is on disk.
        process: The worker process, watched so an early death is not mistaken for a
            slow start.

    Raises:
        RuntimeError: When the worker exits before signalling, or the timeout elapses.
    """
    deadline = time.monotonic() + _READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if sentinel.exists():
            return
        if process.poll() is not None:
            raise RuntimeError(
                "SIGKILL worker exited before signalling readiness; no footerless artefact"
            )
        time.sleep(_POLL_INTERVAL_SECONDS)
    raise RuntimeError("SIGKILL worker did not signal readiness within the timeout")


def inject_disk_full(root: Path, partial_rows: int) -> InjectedFault:
    """Leave a partial trailing episode in the packed data, with `meta/episodes` stale.

    Models a disk-full that flushed a partial episode's rows into the packed parquet but
    never committed the matching metadata update: the data now holds an episode
    `meta/episodes` does not describe. The packed parquet keeps a valid footer (the row
    group flushed) so the partial episode is *readable* — which is what lets the
    truncate means find and drop it and the rebuild means restate the metadata.

    Args:
        root: The dataset root of a valid baseline dataset.
        partial_rows: How many rows the partial trailing episode holds.

    Returns:
        (InjectedFault) Describing the partial episode and the stale metadata.

    Raises:
        RuntimeError: When the dataset has no packed data parquet to extend.
    """
    parquets = data_parquets(root)
    if not parquets:
        raise RuntimeError(f"no packed data parquet under {root}; cannot inject a partial episode")
    parquet = parquets[-1]
    table = pq.read_table(parquet)
    partial_index = _next_episode_index(table)
    partial = _forge_partial_episode(table, partial_rows, partial_index)
    combined = pa.concat_tables([table, partial])
    pq.write_table(combined, parquet)
    return InjectedFault(
        kind=FaultKind.DISK_FULL,
        description=(
            f"partial episode {partial_index} ({partial_rows} rows) appended to {parquet.name}; "
            "meta/episodes not updated"
        ),
        footerless_parquet=None,
        partial_episode_index=partial_index,
        stale_meta=True,
        unmatched_video=None,
    )


def _next_episode_index(table: pa.Table) -> int:
    """The episode index one past the highest present in the packed table."""
    values = table.column(EPISODE_INDEX_COLUMN).to_pylist()
    return (max(int(value) for value in values) + 1) if values else 0


def _forge_partial_episode(table: pa.Table, partial_rows: int, partial_index: int) -> pa.Table:
    """Build a partial-episode row block from the table's own schema and first rows.

    The block reuses the first `partial_rows` rows as feature templates so every column
    keeps its dtype, then overrides the three positional columns — `episode_index`,
    `frame_index`, `index` — to place the rows as a new trailing episode.

    Args:
        table: The packed data table to extend.
        partial_rows: Row count of the partial episode.
        partial_index: The episode index to stamp on the block.

    Returns:
        (pa.Table) The partial-episode rows, schema-identical to `table`.
    """
    total_rows = table.num_rows
    block = table.slice(0, partial_rows)
    block = _override_column(
        block, EPISODE_INDEX_COLUMN, [partial_index] * partial_rows, table.schema
    )
    block = _override_column(block, FRAME_INDEX_COLUMN, list(range(partial_rows)), table.schema)
    return _override_column(
        block, INDEX_COLUMN, list(range(total_rows, total_rows + partial_rows)), table.schema
    )


def _override_column(table: pa.Table, name: str, values: list[int], schema: pa.Schema) -> pa.Table:
    """Replace one column's values, preserving its declared dtype."""
    field_index = schema.get_field_index(name)
    dtype = schema.field(name).type
    array = pa.array(values, type=dtype)
    return table.set_column(field_index, name, array)


def inject_network_cut(root: Path, video_key: str) -> InjectedFault:
    """Leave a video segment on disk that no episode references.

    Models a network cut where a camera segment finished landing but its data episode
    never did: the segment sits under `videos/` with no `meta/episodes` row pointing at
    it. `drop_unmatched_video` is what reconciles the tree by isolating it.

    Args:
        root: The dataset root.
        video_key: The camera key the fabricated segment belongs to.

    Returns:
        (InjectedFault) Describing the unmatched video segment.
    """
    segment = root / VIDEO_SEGMENT_TEMPLATE.format(video_key=video_key, chunk_index=0, file_index=0)
    segment.parent.mkdir(parents=True, exist_ok=True)
    segment.write_bytes(_STUB_VIDEO_BYTES)
    return InjectedFault(
        kind=FaultKind.NETWORK_CUT,
        description=f"video segment {segment.name} for key {video_key!r} referenced by no episode",
        footerless_parquet=None,
        partial_episode_index=None,
        stale_meta=False,
        unmatched_video=segment,
    )
