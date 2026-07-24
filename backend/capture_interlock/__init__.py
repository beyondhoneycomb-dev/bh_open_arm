"""Source-delete interlock for the OpenArm capture pipeline (WP-3C-06).

The raw capture source is deleted only when the converted dataset certifies READY
through the committed WP-3D-05 verifier *and* four capture-preservation checks pass
for every episode: ① the encoded frame count equals the original, ② each video's
declared length equals the episode length, ③ the data-parquet row count equals
`fps × length`, and ④ `capture_ts` is monotonic per slot and content-identical
before and after conversion. Any mismatch preserves the original and flags the
episode; a delete requested against an uncertified source raises — the
`FAIL_BLOCKING` guard against irreversible data loss (`02b` §7.2 WP-3C-06).

This band adds only the capture-preservation layer and the delete gate. The READY
verdict is `backend.dataset.integrity.ensure_training_ready` (imported, never
reimplemented); the converted dataset is read through the committed WP-3D-01 viewer
layout; the raw capture is consumed as data, not code (`WP-3C-02` is a hardware WP
with no code edge, `06` §5.6).
"""

from __future__ import annotations

from backend.capture_interlock.constants import (
    CHECK_CAPTURE_TS,
    CHECK_FRAME_COUNT,
    CHECK_ROW_COUNT,
    CHECK_VIDEO_LENGTH,
    REQUIRED_CAPTURE_CHECKS,
    VERDICT_DELETABLE,
    VERDICT_MISMATCH,
    VERDICT_PRESERVED,
    VERDICT_REFUSED,
)
from backend.capture_interlock.converted import ConvertedDataset, ConvertedReadError
from backend.capture_interlock.interlock import SourceDeleteInterlock
from backend.capture_interlock.preservation import (
    capture_ts_content_hash,
    check_capture_ts,
    check_episode,
    check_frame_count,
    check_row_count,
    check_video_length,
)
from backend.capture_interlock.report import (
    CaptureInterlockError,
    CheckStatus,
    DeleteDecision,
    DeleteOutcome,
    EpisodePreservation,
    PreservationCheck,
)
from backend.capture_interlock.source import (
    CaptureSource,
    CaptureSourceEpisode,
    CaptureSourceError,
)

__all__ = [
    "CHECK_CAPTURE_TS",
    "CHECK_FRAME_COUNT",
    "CHECK_ROW_COUNT",
    "CHECK_VIDEO_LENGTH",
    "REQUIRED_CAPTURE_CHECKS",
    "VERDICT_DELETABLE",
    "VERDICT_MISMATCH",
    "VERDICT_PRESERVED",
    "VERDICT_REFUSED",
    "CaptureInterlockError",
    "CaptureSource",
    "CaptureSourceEpisode",
    "CaptureSourceError",
    "CheckStatus",
    "ConvertedDataset",
    "ConvertedReadError",
    "DeleteDecision",
    "DeleteOutcome",
    "EpisodePreservation",
    "PreservationCheck",
    "SourceDeleteInterlock",
    "capture_ts_content_hash",
    "check_capture_ts",
    "check_episode",
    "check_frame_count",
    "check_row_count",
    "check_video_length",
]
