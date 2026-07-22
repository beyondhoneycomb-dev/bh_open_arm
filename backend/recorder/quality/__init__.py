"""Recorder quality, label and store band (WP-3B-12, `02b` §5.2 "라벨 · 품질 리포트 · 저장소").

This band turns a recorded episode into a judged, quality-measured, safely-stored unit. It
consumes the WP-3B-11 recorder's output — the per-frame episode buffer and the parquet it
writes — and never re-records: a label or quality edit writes a JSON sidecar beside the
data, so the parquet and mp4 are addressed by no path here (`02b` §5.2 WP-3B-12 ①). Channel
roles and the capture join are consumed from the frozen `CTR-REC@v1` / `CTR-CAP@v1`
contracts, not restated.

The layers:

- `label` — the episode judgment: an automatic SUGGESTION and a human verdict, both kept,
  the human's overriding, a mismatch left queryable; an abort or crash label must carry a
  reason and is never auto-saved (②④⑤, and the "discard without a reason" FAIL_BLOCKING).
- `metrics` — the seven measures (loop rate, jitter, missing, CAN drop, camera drop, jerk,
  std floor), each a pure function of a recorded series; CAN drop is surfaced rather than
  hidden behind the recorder's stale-state reuse (③).
- `report` — the `FrameSample` the recorder holds, the `QualityReport` it assembles, and a
  gate that grades only against caller-supplied thresholds — none baked in, because the bar
  is `[결정필요]` (⑥).
- `store` — the layout authority: where the quality sidecar and a quarantined file live.
- `sidecar` — the on-disk episode sidecar read/write; the no-re-record property lives here.
- `diskwatch` — the free-space watch that safe-stores and stops when the disk runs low, the
  in-flight episode aborted with a reason and not auto-saved.
- `crash` — footerless-parquet detection, isolation, an honest recovery attempt, and a
  pending-judgment label that requires a human and is never auto-saved.
"""

from __future__ import annotations

from backend.recorder.quality.crash import (
    RecoveryOutcome,
    attempt_recovery,
    is_footerless_parquet,
    isolate,
    recover,
)
from backend.recorder.quality.diskwatch import (
    DiskDecision,
    DiskStatus,
    DiskWatch,
    StopOutcome,
)
from backend.recorder.quality.label import (
    AbortReason,
    EpisodeLabel,
    EpisodeStatus,
    Judgment,
    Provenance,
    QualityLabelError,
    Verdict,
)
from backend.recorder.quality.metrics import (
    CameraDropStats,
    CanDropStats,
    JerkStats,
    LoopTiming,
    StdFloorStats,
)
from backend.recorder.quality.report import (
    FrameSample,
    GateOutcome,
    QualityReport,
    QualityThresholds,
    build_report,
    evaluate,
)
from backend.recorder.quality.sidecar import (
    EpisodeSidecar,
    SidecarNotFoundError,
    read_sidecar,
    update_label,
    write_sidecar,
)
from backend.recorder.quality.store import DatasetStore

__all__ = [
    "AbortReason",
    "CameraDropStats",
    "CanDropStats",
    "DatasetStore",
    "DiskDecision",
    "DiskStatus",
    "DiskWatch",
    "EpisodeLabel",
    "EpisodeSidecar",
    "EpisodeStatus",
    "FrameSample",
    "GateOutcome",
    "JerkStats",
    "Judgment",
    "LoopTiming",
    "Provenance",
    "QualityLabelError",
    "QualityReport",
    "QualityThresholds",
    "RecoveryOutcome",
    "SidecarNotFoundError",
    "StdFloorStats",
    "StopOutcome",
    "Verdict",
    "attempt_recovery",
    "build_report",
    "evaluate",
    "is_footerless_parquet",
    "isolate",
    "read_sidecar",
    "recover",
    "update_label",
    "write_sidecar",
]
