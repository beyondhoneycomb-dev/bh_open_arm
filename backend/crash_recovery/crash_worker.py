"""A subprocess that writes a real parquet row group then blocks before its footer.

Spawned by `faults.inject_sigkill` to reproduce a *genuine* SIGKILL crash rather than
a hand-truncated file. It opens a `ParquetWriter`, writes one row group (real data,
flushed to the file descriptor by pyarrow's unbuffered `OSFile`), signals readiness by
creating a sentinel file, then blocks forever. The parent SIGKILLs it while it blocks,
so the file left on disk carries data but no footer and no trailing `PAR1` magic — the
crash signature WP-3B-12 ⑤ detects, produced here by an actual kill.

Run as `python -m backend.crash_recovery.crash_worker <parquet> <sentinel> <rows>`.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

# The parent blocks on a sentinel, never on a fixed sleep, so the kill is deterministic
# regardless of machine speed; this is only the idle interval once readiness is
# signalled, long enough that the process is always killed mid-block.
_BLOCK_SECONDS = 3600


def main(argv: list[str]) -> int:
    """Write one row group, signal readiness, then block until killed.

    Args:
        argv: `[_, parquet_path, sentinel_path, rows]`.

    Returns:
        (int) Never returns normally; the parent kills the process. Returns 0 only if
            the block is somehow interrupted, which the parent treats as a failed
            injection.
    """
    parquet_path = Path(argv[1])
    sentinel_path = Path(argv[2])
    rows = int(argv[3])
    parquet_path.parent.mkdir(parents=True, exist_ok=True)

    table = pa.table(
        {
            "frame_index": list(range(rows)),
            "value": [float(index) for index in range(rows)],
        }
    )
    writer = pq.ParquetWriter(parquet_path, table.schema)
    writer.write_table(table)
    # The row group is on disk; the footer is written by writer.close(), which is
    # never called. Signalling readiness here guarantees the parent's kill lands after
    # the data write and before any footer could exist.
    sentinel_path.write_text("ready", encoding="utf-8")

    time.sleep(_BLOCK_SECONDS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
