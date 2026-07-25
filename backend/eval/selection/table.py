"""The checkpoint↔success-rate accumulation table and the CI-based selection rule.

`02c` §3.6 산출: this is the "체크포인트↔성공률 누적 표" plus the "선택 규칙". The
table accumulates `CheckpointScorecard`s (a checkpoint may appear more than once —
repeated evaluation runs of its rollout set), and `select_for_task` is the selection
rule, which is the load-bearing part of the WP:

- **Selection is by real success rate with its CI, never by a point estimate and
  never by an offline metric.** It delegates to the committed WP-4C-03
  `compare_checkpoints`, so it inherits `FR-INF-063`'s refusals: fewer than two
  independent runs, or a sub-threshold (N<20) run, is UNDETERMINED.
- **Overlapping Wilson intervals are UNDETERMINED (CG-4C-06d).** A leader is issued
  only when its interval separates it above EVERY rival; the first overlap makes the
  whole selection UNDETERMINED. Ranking overlapping intervals is ranking noise, and
  a forced rank is never one of the outputs (`02c` §3.6 음성 분기 ④).

Nothing here reads `offline_metrics`. Selection uses success counts alone; the
static check (`staticcheck`) proves this package has no sort/select/delete path that
consumes `val_loss` or `action_mse`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from backend.eval.selection.constants import (
    ROBOMIMIC_WARNING,
    SELECTION_NO_CANDIDATES,
    SELECTION_SELECTED,
    SELECTION_SOLE_CANDIDATE,
    SELECTION_UNDETERMINED,
)
from backend.eval.selection.scorecard import CheckpointScorecard
from backend.eval.stats import (
    VERDICT_A_BETTER,
    CheckpointComparison,
    SuccessRateReport,
    compare_checkpoints,
)

# WP-4A-05 lineage identity: the table is keyed by `CheckpointId`, the same identity
# the scorecard and the reports carry.
from backend.training.lineage import CheckpointId

_UNDETERMINED_REASON = (
    "겹치는 Wilson CI / 단일 실행 / N<20 중 하나로 우열 미판정 — 강제 순위 부여 금지 (CG-4C-06d)"
)
_SELECTED_REASON = "리더의 Wilson CI가 모든 경쟁 체크포인트보다 상위로 분리됨"
_SOLE_REASON = "후보 체크포인트가 1개 — 비교 대상 없음"
_NONE_REASON = "해당 (태스크, 조건)의 후보 체크포인트 없음"


@dataclass(frozen=True)
class SelectionResult:
    """The outcome of a checkpoint selection for one (task, condition).

    `selected` is a `CheckpointId` only when the interval evidence separates a
    single leader above every rival (`verdict == SELECTION_SELECTED`) or when there
    is exactly one candidate (`SELECTION_SOLE_CANDIDATE`). Every ambiguous case —
    an overlapping CI, a single run, a sub-threshold sample — is
    `SELECTION_UNDETERMINED` with `selected` None, so a forced rank cannot leak out.

    Attributes:
        task: The task selected for.
        condition: The generic condition value selected under.
        verdict: One of the four `SELECTION_*` values.
        selected: The chosen checkpoint, or None when undetermined / no candidates.
        comparisons: The pairwise leader-vs-rival comparisons, evidence for the
            verdict; empty for the sole-candidate and no-candidate cases.
        reason: Why this verdict.
    """

    task: str
    condition: str
    verdict: str
    selected: CheckpointId | None
    comparisons: tuple[CheckpointComparison, ...]
    reason: str

    def render(self) -> str:
        """Render the selection outcome with the robomimic warning stamped first.

        The warning rides every selection surface (CG-4C-06b). The body is Korean
        report content; this docstring stays English.

        Returns:
            (str) The rendered selection result.
        """
        selected = (
            f"{self.selected.output_dir}@{self.selected.step}"
            if self.selected is not None
            else "없음"
        )
        lines = [
            ROBOMIMIC_WARNING,
            "",
            f"체크포인트 선택 [{self.task} / {self.condition}]",
            f"판정: {self.verdict}",
            f"선택된 체크포인트: {selected}",
            f"근거: {self.reason}",
        ]
        for comparison in self.comparisons:
            lines.append(
                f"  비교: {comparison.checkpoint_a.output_dir}@{comparison.checkpoint_a.step} vs "
                f"{comparison.checkpoint_b.output_dir}@{comparison.checkpoint_b.step} "
                f"-> {comparison.verdict} ({comparison.reason})"
            )
        return "\n".join(lines)


class ScorecardTable:
    """Accumulates checkpoint scorecards and applies the CI-based selection rule.

    Ownership/threading: an in-memory accumulator with no external state; not
    synchronised, so a caller sharing one across threads guards it itself. A
    checkpoint may be added more than once — each add is one evaluation run, and
    selection pools a checkpoint's runs the way WP-4C-03's comparison does.
    """

    def __init__(self) -> None:
        """Create an empty table."""
        self.mScorecards: dict[CheckpointId, list[CheckpointScorecard]] = defaultdict(list)

    def add(self, scorecard: CheckpointScorecard) -> None:
        """Validate and accumulate one checkpoint scorecard (one evaluation run).

        Args:
            scorecard: The scorecard to add; validated before it is stored.

        Raises:
            CheckpointScorecardError: When the scorecard is structurally invalid.
        """
        scorecard.validate()
        self.mScorecards[scorecard.checkpoint].append(scorecard)

    def checkpoints(self) -> tuple[CheckpointId, ...]:
        """Return the accumulated checkpoints, ordered by identity for determinism."""
        return tuple(
            sorted(
                self.mScorecards, key=lambda checkpoint: (checkpoint.output_dir, checkpoint.step)
            )
        )

    def scorecards_for(self, checkpoint: CheckpointId) -> tuple[CheckpointScorecard, ...]:
        """Return every scorecard accumulated for one checkpoint (its eval runs)."""
        return tuple(self.mScorecards.get(checkpoint, ()))

    def runs_for(
        self, checkpoint: CheckpointId, task: str, condition: str
    ) -> tuple[SuccessRateReport, ...]:
        """Return a checkpoint's success-rate reports for one (task, condition).

        These are the independent runs `compare_checkpoints` pools — one per
        accumulated scorecard that carries this (task, condition).

        Args:
            checkpoint: The checkpoint whose runs to collect.
            task: The task to filter to.
            condition: The generic condition value to filter to.

        Returns:
            (tuple[SuccessRateReport, ...]) The matching reports, in add order.
        """
        reports: list[SuccessRateReport] = []
        for scorecard in self.mScorecards.get(checkpoint, ()):
            report = scorecard.report_for(task, condition)
            if report is not None:
                reports.append(report)
        return tuple(reports)

    def select_for_task(self, task: str, condition: str) -> SelectionResult:
        """Select the best checkpoint for a (task, condition) by success-rate CIs.

        The selection rule (`02c` §3.6): a checkpoint is chosen only when its Wilson
        interval separates it above every rival. The leader (highest pooled success
        rate) is compared against each other candidate through the committed
        `compare_checkpoints`; the first UNDETERMINED comparison — an overlapping CI,
        a single run, or a sub-threshold sample — makes the whole selection
        UNDETERMINED (CG-4C-06d). No offline metric enters this decision.

        Args:
            task: The task to select for.
            condition: The generic condition value to select under.

        Returns:
            (SelectionResult) The selection outcome and its comparison evidence.
        """
        candidates = {
            checkpoint: self.runs_for(checkpoint, task, condition)
            for checkpoint in self.checkpoints()
        }
        candidates = {checkpoint: runs for checkpoint, runs in candidates.items() if runs}

        if not candidates:
            return SelectionResult(task, condition, SELECTION_NO_CANDIDATES, None, (), _NONE_REASON)
        if len(candidates) == 1:
            sole = next(iter(candidates))
            return SelectionResult(
                task, condition, SELECTION_SOLE_CANDIDATE, sole, (), _SOLE_REASON
            )

        leader = self._leader(candidates)
        comparisons: list[CheckpointComparison] = []
        separated = True
        for rival, rival_runs in candidates.items():
            if rival == leader:
                continue
            comparison = compare_checkpoints(candidates[leader], rival_runs)
            comparisons.append(comparison)
            if not (comparison.is_ranked and comparison.verdict == VERDICT_A_BETTER):
                separated = False

        if separated:
            return SelectionResult(
                task, condition, SELECTION_SELECTED, leader, tuple(comparisons), _SELECTED_REASON
            )
        return SelectionResult(
            task, condition, SELECTION_UNDETERMINED, None, tuple(comparisons), _UNDETERMINED_REASON
        )

    def render_table(self, condition: str) -> str:
        """Render the accumulation table for one condition, warning stamped first.

        Args:
            condition: The condition value the rows are shown for.

        Returns:
            (str) The rendered table.
        """
        lines = [ROBOMIMIC_WARNING, "", f"체크포인트↔성공률 누적 표 (조건: {condition})"]
        for checkpoint in self.checkpoints():
            hashed = f"{checkpoint.output_dir}@{checkpoint.step}"
            for scorecard in self.scorecards_for(checkpoint):
                for entry in scorecard.per_task:
                    if entry.condition != condition:
                        continue
                    report = entry.report
                    wilson = report.ci_wilson_95
                    lines.append(
                        f"  {hashed} [{entry.task}] 성공률 {report.point_estimate:.4f} "
                        f"Wilson95 [{wilson.lower:.4f}, {wilson.upper:.4f}] (N={report.n_trials})"
                    )
        return "\n".join(lines)

    @staticmethod
    def _leader(candidates: Mapping[CheckpointId, Sequence[SuccessRateReport]]) -> CheckpointId:
        """Return the candidate with the highest pooled success rate.

        The leader is picked by pooled point estimate — a success rate, computed
        from success counts alone — not by any offline metric. Ties are broken by
        checkpoint identity so the choice is deterministic; a tie's overlapping CIs
        then make the comparison UNDETERMINED, which is the correct outcome.
        """
        leader: CheckpointId | None = None
        leader_point = -1.0
        for checkpoint in sorted(candidates, key=lambda item: (item.output_dir, item.step)):
            point = _pooled_point(candidates[checkpoint])
            if point > leader_point:
                leader_point = point
                leader = checkpoint
        assert leader is not None
        return leader


def _pooled_point(runs: Sequence[SuccessRateReport]) -> float:
    """The pooled success-rate point estimate across a checkpoint's runs.

    Pools the binomial trials the way WP-4C-03's comparison does — more trials, one
    proportion. Uses success counts only; no offline metric is involved.
    """
    n_success = sum(run.n_success for run in runs)
    n_trials = sum(run.n_trials for run in runs)
    return n_success / n_trials
