"""WP-4C-07 phase-1 — optional auto-success-judge + disagreement aggregation.

`02c` §3.7 (`FR-INF-079`, `FR-SIM-095`, `11` §5-Q11). The offline half of the optional
VLM auto-judge: the judge adapter, the disagreement aggregator, the auto-disable
trigger, the Q11-order enable gate, and the GPU preflight. It never fakes a rollout
label or a human label — the real Cosmos Reason 2 run and the human reference labels
(WP-4C-02) are DEFERRED — so it is exercised on synthetic inputs.

The load-bearing invariants, each enforced in code, not convention:

- **Canon is the human label** (`FR-INF-079`). `canon_episodes` is the only bridge to
  WP-4C-03's aggregator and yields HUMAN-sourced records only; a MODEL label never
  reaches the canon (CG-4C-07a).
- **Disagreement over threshold disables** (`FR-INF-079`). `evaluate_disable` moves an
  ENABLED judge to DISABLED_REQUIRE_HUMAN — a required normal transition, not a gate
  failure (CG-4C-07b). A human AMBIGUOUS label is the second disable trigger
  (`02c` §3.4).
- **Model-judged is tagged distinctly** (`FR-SIM-095`). Every model label carries a
  `model-judged` sidecar; a human label is `human-labeled` (CG-4C-07c).
- **Cosmos Reason 2 needs Hopper/Blackwell** (`FR-SIM-095`). The preflight renders
  per-target eligibility over the owned fleet — RTX 5090 eligible, RTX A6000 not
  (CG-4C-07d).
- **The Q11 order is the WP** (`11` §5-Q11). `enable_autojudge` is the sole producer
  of the ENABLED state and refuses any order but human labels -> criteria ->
  precision/recall (CG-4C-07e).
"""

from __future__ import annotations

from backend.eval.autojudge.adapter import (
    AutoJudgeDeferredError,
    CosmosReason2Judge,
    JudgeRequest,
    JudgeVerdict,
    VlmJudge,
    judge_episode,
)
from backend.eval.autojudge.agreement import (
    AgreementError,
    AgreementReport,
    JudgmentPair,
    aggregate_agreement,
    pair_judgments,
)
from backend.eval.autojudge.constants import (
    COSMOS_REASON_2,
    DEFAULT_DISAGREEMENT_THRESHOLD,
    Q11_ORDER,
    SIDECAR_TAG_HUMAN_LABELED,
    SIDECAR_TAG_MODEL_JUDGED,
)
from backend.eval.autojudge.enablement import (
    AutoJudgeState,
    Q11OrderError,
    Q11Readiness,
    can_enable_autojudge,
    enable_autojudge,
)
from backend.eval.autojudge.labels import (
    JudgedEpisode,
    JudgeSidecar,
    LabelProvenanceError,
    LabelSource,
    canon_episodes,
    model_labels_excluded_from_canon,
    sidecar_records,
)
from backend.eval.autojudge.preflight import (
    GpuPreflightResult,
    eligible_targets,
    fleet_has_eligible_target,
    preflight_fleet,
    preflight_target,
)
from backend.eval.autojudge.trigger import (
    DisableDecision,
    default_threshold,
    evaluate_disable,
    has_ambiguous_label,
)

__all__ = [
    "COSMOS_REASON_2",
    "DEFAULT_DISAGREEMENT_THRESHOLD",
    "Q11_ORDER",
    "SIDECAR_TAG_HUMAN_LABELED",
    "SIDECAR_TAG_MODEL_JUDGED",
    "AgreementError",
    "AgreementReport",
    "AutoJudgeDeferredError",
    "AutoJudgeState",
    "CosmosReason2Judge",
    "DisableDecision",
    "GpuPreflightResult",
    "JudgeRequest",
    "JudgeSidecar",
    "JudgeVerdict",
    "JudgedEpisode",
    "JudgmentPair",
    "LabelProvenanceError",
    "LabelSource",
    "Q11OrderError",
    "Q11Readiness",
    "VlmJudge",
    "aggregate_agreement",
    "can_enable_autojudge",
    "canon_episodes",
    "default_threshold",
    "eligible_targets",
    "enable_autojudge",
    "evaluate_disable",
    "fleet_has_eligible_target",
    "has_ambiguous_label",
    "judge_episode",
    "model_labels_excluded_from_canon",
    "pair_judgments",
    "preflight_fleet",
    "preflight_target",
    "sidecar_records",
]
