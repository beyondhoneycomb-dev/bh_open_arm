"""Named constants for the WP-3C-06 source-delete interlock (`02b` §7.2).

The interlock answers one question, and it is not the question WP-3D-05 answers.
WP-3D-05 asks whether a *converted* dataset is internally whole enough to train on
(`ensure_training_ready`). This band asks a second, orthogonal question: did the
conversion *preserve the raw capture* it was made from? Four capture-preservation
checks compare the raw source against the converted dataset — frame count, video
length, row count, and `capture_ts` — and the raw source is deleted only when the
converted dataset certifies READY (WP-3D-05) *and* all four preservation checks
pass. Any mismatch preserves the original and flags the episode; a delete with any
check unmet is `FAIL_BLOCKING`, because it is irreversible data loss (`02b` §7.2
WP-3C-06, `NFR-CAM-007`, `FR-CAM-032`/`035`).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Raw capture source layout (the pre-conversion output, consumed as data)
# ---------------------------------------------------------------------------

# The raw source holds one directory per episode; each directory carries a small
# manifest (fps + original frame count) and the CTR-CAP@v1 capture-timestamp
# sidecar as flat records. These two files are the ground truth the conversion is
# checked to have preserved — the manifest fixes "the original frame count", the
# sidecar fixes the per-frame capture instants that check ④ hashes before/after.
RAW_EPISODE_DIR_TEMPLATE = "episode-{episode_index:06d}"
RAW_MANIFEST_FILENAME = "capture.json"
RAW_CAPTURE_TS_FILENAME = "capture_ts.json"

# The manifest's keys. `length` is the original grabbed frame count N; `fps` is the
# capture rate. Every preservation check is anchored to these two numbers.
MANIFEST_EPISODE_INDEX_KEY = "episode_index"
MANIFEST_FPS_KEY = "fps"
MANIFEST_LENGTH_KEY = "length"

# ---------------------------------------------------------------------------
# Converted dataset — the preserved capture_ts sidecar and the flag output
# ---------------------------------------------------------------------------

# The converted v3.0 dataset carries the preserved capture_ts sidecar under
# `meta/capture/` (one file per episode, the same CTR-CAP@v1 flat records the raw
# source holds). It is orthogonal to the files WP-3D-05 reads, so a dataset that
# carries it still verifies READY unchanged; check ④ compares its content hash to
# the raw source's.
CONVERTED_CAPTURE_DIR = "meta/capture"
CONVERTED_CAPTURE_SIDECAR_TEMPLATE = "meta/capture/episode-{episode_index:06d}.json"

# Where an episode that failed a preservation check is flagged. The flag is written
# into the converted dataset (a runtime data artifact, not the WP-3D-05 code tree),
# never into the raw source — the raw source is preserved byte-for-byte, untouched.
FLAG_DIR = "meta/capture/flags"
FLAG_SIDECAR_TEMPLATE = "meta/capture/flags/episode-{episode_index:06d}.json"

# ---------------------------------------------------------------------------
# The four capture-preservation checks (`02b` §7.2 WP-3C-06)
# ---------------------------------------------------------------------------

# ① every converted stream's encoded frame count equals the original frame count.
CHECK_FRAME_COUNT = "frame_count_matches_original"
# ② the converted video's declared temporal length equals the episode length.
CHECK_VIDEO_LENGTH = "video_length_matches_episode_length"
# ③ the converted data-parquet row count equals `fps × episode length`.
CHECK_ROW_COUNT = "row_count_matches_fps_times_length"
# ④ the converted capture_ts is monotonic per slot and preserved (before/after
#    content-hash compare against the raw source).
CHECK_CAPTURE_TS = "capture_ts_monotonic_and_preserved"

# READY is not one of the four; it is the WP-3D-05 gate the delete decision layers
# the four on top of. Named so the decision can report which layer refused.
CHECK_TRAINING_READY = "converted_dataset_training_ready"

# The full required set. A delete is certified only when every one of the four
# passes for every episode AND the converted dataset is READY. Narrowing this set
# cannot certify a delete — the report requires the whole set ran.
REQUIRED_CAPTURE_CHECKS = (
    CHECK_FRAME_COUNT,
    CHECK_VIDEO_LENGTH,
    CHECK_ROW_COUNT,
    CHECK_CAPTURE_TS,
)

# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------

# An episode's preservation verdict — every check passed, or at least one bit.
VERDICT_PRESERVED = "PRESERVED"
VERDICT_MISMATCH = "MISMATCH"

# The delete decision. `DELETABLE` only when READY and every episode PRESERVED;
# `REFUSED` otherwise, and a REFUSED decision deletes nothing.
VERDICT_DELETABLE = "DELETABLE"
VERDICT_REFUSED = "REFUSED"

# The content-hash algorithm for the capture_ts before/after compare (④). SHA-256
# over the canonical per-slot capture instant sequence, so the same timestamps hash
# the same on any machine and a reorder or drop changes the digest.
CAPTURE_TS_HASH_ALGORITHM = "sha256"
