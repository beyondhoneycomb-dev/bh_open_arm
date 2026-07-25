"""WP-4C-06 — the checkpoint-selection scorecard and its policy (`02c` §3.6).

This package builds the checkpoint↔success-rate accumulation table, the selection
rule, and the val-loss-auto-select block. Its product is deliberately NOT automation:
it assembles the table, blocks ranking by anything but real success rate, and hands
the decision to a human (`02c` §3.6 워크플로우 형상). The load-bearing invariants are
enforced in code, not by convention:

- **`offline_metrics` is a field, never a key** (`FR-INF-062`, CG-4C-06a). `val_loss`
  and `action_mse` are shown but never sorted, compared, or deleted by — proven by
  the `staticcheck` AST scan, which the tests run on this tree and on violation
  fixtures.
- **The robomimic warning is unconditional** (`FR-GUI-125`, CG-4C-06b): every
  scorecard and selection render stamps "offline metrics do not predict online
  success" first.
- **Overlapping Wilson CIs are undetermined** (CG-4C-06d): selection delegates to
  the committed WP-4C-03 `compare_checkpoints`, so a forced rank cannot leak out.
- **The four `FR-TRN-040` frequencies stay four meanings** (CG-4C-06e), with
  `env_eval_freq` marked unrelated to real OpenArm.
- **The selection decision is recorded in lineage** (CG-4C-06f): recorded THROUGH
  the committed WP-4A-05 store, with who and on-what-basis.

It reuses the committed WP-4C-03 `SuccessRateReport`/`compare_checkpoints` and WP-4A-05
lineage; it consumes the condition as a generic value, not WP-4C-05's enum
(`02c` §3.6 DO-NOT-DUPLICATE). The real rollout/label population is DEFERRED (Human/
HW); this package is exercised on synthetic reports.
"""

from __future__ import annotations

from backend.eval.selection.constants import (
    CONDITION_NOMINAL,
    CONDITION_PERTURBED,
    ENV_EVAL_FREQ_NOTE,
    GENERALIZATION_GAP_UNMEASURED,
    OFFLINE_METRIC_FIELDS,
    ROBOMIMIC_WARNING,
    SELECTION_NO_CANDIDATES,
    SELECTION_SELECTED,
    SELECTION_SOLE_CANDIDATE,
    SELECTION_UNDETERMINED,
)
from backend.eval.selection.decision import (
    SelectionDecision,
    SelectionDecisionError,
    SelectionDecisionRecorder,
)
from backend.eval.selection.scorecard import (
    CheckpointScorecard,
    CheckpointScorecardError,
    FrequencyConfig,
    OfflineMetrics,
    PerTaskReport,
)
from backend.eval.selection.staticcheck import StaticViolation, scan_source, scan_tree
from backend.eval.selection.table import ScorecardTable, SelectionResult

__all__ = [
    "CONDITION_NOMINAL",
    "CONDITION_PERTURBED",
    "ENV_EVAL_FREQ_NOTE",
    "GENERALIZATION_GAP_UNMEASURED",
    "OFFLINE_METRIC_FIELDS",
    "ROBOMIMIC_WARNING",
    "SELECTION_NO_CANDIDATES",
    "SELECTION_SELECTED",
    "SELECTION_SOLE_CANDIDATE",
    "SELECTION_UNDETERMINED",
    "CheckpointScorecard",
    "CheckpointScorecardError",
    "FrequencyConfig",
    "OfflineMetrics",
    "PerTaskReport",
    "ScorecardTable",
    "SelectionDecision",
    "SelectionDecisionError",
    "SelectionDecisionRecorder",
    "SelectionResult",
    "StaticViolation",
    "scan_source",
    "scan_tree",
]
