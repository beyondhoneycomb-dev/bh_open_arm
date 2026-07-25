"""Fixed values of the WP-4C-06 checkpoint-selection policy (`02c` §3.6).

Every literal here is a decision the spec made (`FR-INF-062`, `FR-TRN-040`,
`FR-TRN-042`, `FR-GUI-125`), not a knob this package invented. The load-bearing
ones are the offline-metric field names — the two symbols the static check
(`staticcheck`) forbids from ever reaching a sort/selection/delete context — and
the robomimic warning text, which the scorecard renderer stamps unconditionally.
"""

from __future__ import annotations

# CG-4C-06b / FR-INF-062 / FR-GUI-125: the robomimic warning is shown ALWAYS, on
# every scorecard render. Removing it, or gating it behind a flag, is the exact
# omission FR-GUI-125 forbids: the whole point of the WP is that the offline
# numbers are visible AND permanently disclaimed. The English clause is the
# robomimic study's own wording, kept verbatim so the citation is checkable.
ROBOMIMIC_WARNING = (
    "경고: 오프라인 지표(val loss / action MSE)는 온라인 성공률을 예측하지 못한다. "
    'robomimic: "the best validation policy is 50 to 100% worse than the best '
    'performing policy". 체크포인트 선택은 실기 성공률(Wilson 95% CI)로만 하며, '
    "오프라인 지표는 표시 전용이고 정렬·선택 키가 될 수 없다."
)

# `02c` §3.6 interface contract: `offline_metrics` is a FIELD that must never be a
# sort/selection key. These are the two field names the static check treats as
# forbidden the moment they appear in a sort, comparison, or delete context.
OFFLINE_METRIC_VAL_LOSS = "val_loss"
OFFLINE_METRIC_ACTION_MSE = "action_mse"
OFFLINE_METRIC_FIELDS = frozenset({OFFLINE_METRIC_VAL_LOSS, OFFLINE_METRIC_ACTION_MSE})

# The label the renderer stamps beside the offline metrics so a reader cannot
# mistake a displayed value for a rankable one (`02c` §3.6: display-but-not-sortable).
OFFLINE_METRICS_DISPLAY_ONLY = "표시 전용 — 정렬·선택 키가 아니다 (FR-INF-062)"

# CG-4C-06e / FR-TRN-040: four training frequencies with FOUR distinct meanings,
# never one collapsed "evaluation period". `eval_steps` is a held-out OFFLINE eval
# loss cadence (an offline metric, not a selection basis); `env_eval_freq` is a
# sim-rollout cadence that has nothing to do with real-OpenArm success.
FREQ_LOG = "log_freq"
FREQ_SAVE = "save_freq"
FREQ_EVAL_STEPS = "eval_steps"
FREQ_ENV_EVAL = "env_eval_freq"

FREQ_MEANINGS = {
    FREQ_LOG: "학습 지표 로깅 주기(스텝) — 기록·표시용",
    FREQ_SAVE: "체크포인트 저장 주기(스텝) — 무엇을 남길지",
    FREQ_EVAL_STEPS: "held-out 검증 손실(eval loss) 주기(스텝) — 오프라인 지표(선택 근거 아님)",
    FREQ_ENV_EVAL: "시뮬 롤아웃 평가 주기(스텝)",
}

# CG-4C-06e: `env_eval_freq` must carry this note distinctly from the other three —
# a sim rollout cadence is not a real-OpenArm evaluation cadence (`FR-TRN-040`).
ENV_EVAL_FREQ_NOTE = "OpenArm 실기와 무관 (sim rollout — unrelated to real OpenArm)"

# WP-4C-05 owns the `Condition` enum {NOMINAL, PERTURBED}; WP-4C-06 consumes the
# condition as a generic string VALUE (a data-join, no enum import), so the two
# build in parallel with no type dependency (`02c` §3.6 DO-NOT-DUPLICATE). These
# are the join tokens, not a re-declaration of that enum.
CONDITION_NOMINAL = "NOMINAL"
CONDITION_PERTURBED = "PERTURBED"

# The generalization gap = nominal − perturbed is a DERIVED value (`02c` §3.5). With
# PERTURBED deferred until the Wave 3C initial-state distribution lands, the gap is
# unmeasured, and the report must SAY so rather than emit a fabricated number.
GENERALIZATION_GAP_UNMEASURED = (
    "일반화 격차 미측정 (PERTURBED 조건 보류 — Wave 3C 초기상태 분포 미착지)"
)

# Selection outcomes. `SELECTED` is issued only when one checkpoint's Wilson CI
# separates it above every rival; overlapping CIs, single runs, and sub-threshold
# samples all collapse to `UNDETERMINED` (CG-4C-06d) — a forced rank is never one
# of the outputs.
SELECTION_SELECTED = "SELECTED"
SELECTION_UNDETERMINED = "UNDETERMINED"
SELECTION_SOLE_CANDIDATE = "SOLE_CANDIDATE"
SELECTION_NO_CANDIDATES = "NO_CANDIDATES"

# Static-check rules (`staticcheck`). Each is stated as an ABSENCE the selection
# tree must maintain, and each ships a violation fixture proving the scan bites.
RULE_NO_OFFLINE_SORT = (
    "an offline metric (val_loss / action_mse) is used as a sort or selection key (FR-INF-062)"
)
RULE_NO_LOSS_AUTO_DELETE = (
    "a checkpoint is auto-deleted on an offline-metric criterion (FR-TRN-042)"
)

# The call names that constitute an ordering, a selection, or a deletion — the
# contexts in which an offline-metric reference becomes a violation. Reading an
# offline metric to DISPLAY it (an f-string, a render) is none of these and is
# allowed; that is the display-but-not-sortable shape (`02c` §3.6).
SORT_CALLS = frozenset({"sorted", "min", "max"})
SORT_METHODS = frozenset({"sort"})
SELECT_SINKS = frozenset({"select", "auto_select", "select_checkpoint", "choose", "rank"})
DELETE_SINKS = frozenset({"delete", "auto_delete", "remove", "unlink", "prune", "discard", "evict"})
