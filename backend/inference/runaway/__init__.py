"""WP-4A-08 — inference runaway detection, raw/sent dual logging, remote-disconnect classing.

The publisher-side safety monitor of the inference path (SPINE §2-1): it gates policy
output, holds on a fault by **publishing a hold intent** to the committed mailbox (the
`ActuationScheduler` emits the frames; this package never writes CAN), and it reuses —
never re-implements — the committed clamp gateway, queue meter, and Wave 2C stop
category.

Public surface:

- `RunawayDetector` — the producer: NaN/Inf rejection (`FR-INF-042`), the four-condition
  runaway detector (`FR-INF-043`), remote-disconnect handling (`FR-INF-046`), and the
  dual recorder wired together; its verdicts (`ActionVerdict`, `DisconnectVerdict`).
- `RunawayConditions` / `RunawayCondition` / `ConditionSignals` — the four independent
  conditions, each with its own counter so none masks another, plus `RUNAWAY_ERROR_CODE`.
- `RunawayThresholds` + `metering_placeholder_thresholds` — the four thresholds as
  parameters only, values deferred to 4C (SPINE §2-6).
- `DualActionRecorder` / `DualActionRecord` — SPINE §6 action channels verbatim, raw
  request always recoverable, `executedMitCommand` audit-only.
- `classify_remote` / `DisconnectClass` / `RemoteHealth` — transport vs empty-action (vs
  stale, vs queue-wait) to distinct registry codes.
- `InferencePhase` / `FaultKind` — the P3 -> P8 transition this component effects.
"""

from __future__ import annotations

from backend.inference.runaway.conditions import (
    CONDITION_PRIORITY,
    RUNAWAY_ERROR_CODE,
    ConditionSignals,
    RunawayCondition,
    RunawayConditions,
)
from backend.inference.runaway.detector import (
    ActionVerdict,
    DisconnectVerdict,
    RunawayDetector,
)
from backend.inference.runaway.disconnect import (
    DISCONNECT_ERROR_CODES,
    PROTECTIVE_STOP_CATEGORY,
    PROTECTIVE_STOP_STRATEGY,
    DisconnectClass,
    RemoteHealth,
    classify_remote,
    error_code_for,
    is_network_disconnect,
    protective_stop_is_category_two,
)
from backend.inference.runaway.dual_log import DualActionRecord, DualActionRecorder
from backend.inference.runaway.phase import FaultKind, InferencePhase
from backend.inference.runaway.thresholds import (
    RunawayThresholds,
    metering_placeholder_thresholds,
)

__all__ = [
    "CONDITION_PRIORITY",
    "DISCONNECT_ERROR_CODES",
    "PROTECTIVE_STOP_CATEGORY",
    "PROTECTIVE_STOP_STRATEGY",
    "RUNAWAY_ERROR_CODE",
    "ActionVerdict",
    "ConditionSignals",
    "DisconnectClass",
    "DisconnectVerdict",
    "DualActionRecord",
    "DualActionRecorder",
    "FaultKind",
    "InferencePhase",
    "RemoteHealth",
    "RunawayCondition",
    "RunawayConditions",
    "RunawayDetector",
    "RunawayThresholds",
    "classify_remote",
    "error_code_for",
    "is_network_disconnect",
    "metering_placeholder_thresholds",
    "protective_stop_is_category_two",
]
