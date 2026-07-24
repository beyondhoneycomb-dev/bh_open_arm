"""Named constants for the WP-3D-05 dataset integrity verifier (`02b` §8.2).

The verifier answers one question: is a dataset directory whole enough to be a
training input? It reads the same LeRobot v3.0 on-disk convention the WP-3D-01
viewer reads (consumed as data, not our contract, `06` §5.6) and applies seven
checks. READY is earned only when all seven pass; one failure — or a check that did
not run at all — makes the dataset INVALID, and INVALID is never handed to a
trainer (`FR-DAT-051`, `NFR-DAT-005`).
"""

from __future__ import annotations

# A parquet file opens and closes with this 4-byte magic. A crash-truncated file
# that lost its footer also lost the trailing magic, so the trailing signature is
# the cheapest detectable evidence of a footerless file. The footer check reads
# it and then parses the footer proper (`02b` §8.2 WP-3D-05: "parquet footer read").
PARQUET_MAGIC = b"PAR1"
PARQUET_MAGIC_LEN = 4
PARQUET_SUFFIX = ".parquet"
MP4_SUFFIX = ".mp4"

# The seven integrity checks. `READY` requires every one to PASS; a missing check
# is itself FAIL_BLOCKING (`02b` §8.2 WP-3D-05: a missing check fails the build), so
# the report verifies this exact set ran before it will call a dataset READY.
CHECK_PARQUET_FOOTER = "parquet_footer"
CHECK_INFO_CHUNK_CONSISTENCY = "info_chunk_consistency"
CHECK_INDEX_CONTINUITY = "index_continuity"
CHECK_VIDEO_FRAME_COUNT = "video_frame_count"
CHECK_DTYPE_MATCH = "dtype_match"
CHECK_STATS_HASH_MATCH = "stats_hash_match"
# The edit/merge band (WP-3D-02/06) writes an EDIT_INVALID marker into a dataset
# whose sidecar remap failed the content cross-check — a structurally-complete tree
# whose labels are attached to the wrong episodes. The six data checks above cannot
# see that (they never read sidecars), so honouring the marker is what actually bars
# an aborted edit from training; without this check the marker is write-only.
CHECK_NO_EDIT_MARKER = "no_edit_invalid_marker"

REQUIRED_CHECKS = (
    CHECK_PARQUET_FOOTER,
    CHECK_INFO_CHUNK_CONSISTENCY,
    CHECK_INDEX_CONTINUITY,
    CHECK_VIDEO_FRAME_COUNT,
    CHECK_DTYPE_MATCH,
    CHECK_STATS_HASH_MATCH,
    CHECK_NO_EDIT_MARKER,
)

# The verdict a dataset earns. `READY` only when every required check passes; a
# single failure makes it `INVALID`, the state a training-input guard refuses.
VERDICT_READY = "READY"
VERDICT_INVALID = "INVALID"

# `meta/info.json` carries the dataset's own recorded stats content hash under
# this key; the stats-hash check recomputes the hash of `meta/stats.json` and
# compares. The recorded value is stamped by the stats/lineage band (WP-3D-03 ④,
# consumed by WP-3D-04) — the verifier only checks the two still agree.
INFO_STATS_HASH_KEY = "stats_content_hash"
STATS_RELATIVE_PATH = "meta/stats.json"

# Regression bound: verification must not exceed twice the time it takes to
# sequentially read the dataset once (`02b` §8.2 WP-3D-05 ③). The reference
# bandwidth is fio-measured on the target; `bandwidth.measure_sequential_read_
# bandwidth` is the in-repo proxy that reads the dataset's own bytes.
SEQUENTIAL_READ_REGRESSION_MULTIPLIER = 2.0

# The block size a sequential read is chunked into when measuring bandwidth.
SEQUENTIAL_READ_BLOCK_BYTES = 1 << 20
