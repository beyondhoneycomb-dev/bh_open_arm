"""`CheckpointScorecard` — the checkpoint↔success-rate row and its renderer (`02c` §3.6).

The scorecard is the per-checkpoint view of the accumulation table: for one
checkpoint it carries the WP-4A-05 lineage identity, the per-(task, condition)
`SuccessRateReport`s (WP-4C-03, imported unchanged), the DERIVED generalization
gap, and the offline metrics — with the invariants of `FR-INF-062`/`FR-GUI-125`
built into the type and the renderer rather than left to convention:

- **`offline_metrics` is a field, never a key.** `OfflineMetrics` holds `val_loss`
  and `action_mse` so the numbers are visible, but nothing here — no method, no
  ordering — consumes them for a decision. The static check (`staticcheck`) proves
  no code path in this package sorts, compares, or deletes by them.
- **The robomimic warning is unconditional.** `render` stamps it first, every time
  (CG-4C-06b): offline metrics do not predict online success.
- **The generalization gap is derived, never asserted.** `generalization_gap` is
  `nominal − perturbed` when both conditions are present, and `None` otherwise; the
  renderer then states "generalization gap unmeasured" (`02c` §3.5). No confidence
  interval is claimed on the gap — a difference-of-two-binomials CI has no spec
  basis (`02c` §3.5 CG-4C-05b).
- **The four training frequencies are four meanings.** `FrequencyConfig` exposes
  `log_freq`/`save_freq`/`eval_steps`/`env_eval_freq` distinctly, with
  `env_eval_freq` marked unrelated to real OpenArm (CG-4C-06e / `FR-TRN-040`).

The condition is consumed as a generic string value (`CONDITION_NOMINAL` /
`CONDITION_PERTURBED`), not WP-4C-05's enum — a data-join so the two WPs build in
parallel with no type dependency (`02c` §3.6 DO-NOT-DUPLICATE).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.eval.selection.constants import (
    CONDITION_NOMINAL,
    CONDITION_PERTURBED,
    ENV_EVAL_FREQ_NOTE,
    FREQ_ENV_EVAL,
    FREQ_EVAL_STEPS,
    FREQ_LOG,
    FREQ_MEANINGS,
    FREQ_SAVE,
    GENERALIZATION_GAP_UNMEASURED,
    OFFLINE_METRICS_DISPLAY_ONLY,
    ROBOMIMIC_WARNING,
)
from backend.eval.stats import SuccessRateReport

# WP-4A-05 lineage consumption: a scorecard is keyed by the lineage `CheckpointId`,
# so a selection row rides the same immutable identity the checkpoint's eight-element
# snapshot does. This import (with `decision.py`'s) backs the WP-4A-05 -> WP-4C-06
# reference edge (`06` §5.6 / CI-16).
from backend.training.lineage import CheckpointId


class CheckpointScorecardError(ValueError):
    """Raised when a scorecard would violate a WP-4C-06 structural invariant.

    The cases: an empty `per_task`, two entries for the same (task, condition), or
    an empty `lineage_ref`. Each would make the scorecard an unreliable selection
    row — an untraceable checkpoint, or a task whose success rate is ambiguous.
    """


@dataclass(frozen=True)
class OfflineMetrics:
    """The offline training metrics a scorecard displays but never ranks by.

    `02c` §3.6 is explicit that these belong on the card ("표시하되") yet can never
    be a sort or selection key ("정렬 불가"). This type therefore carries the two
    values and nothing that orders them; the guarantee that no code path in this
    package ranks by them is enforced statically (`staticcheck`), because a type
    alone cannot forbid `sorted(cards, key=lambda c: c.offline_metrics.val_loss)`.

    Attributes:
        val_loss: The checkpoint's held-out validation loss.
        action_mse: The checkpoint's action mean-squared-error on held-out data.
    """

    val_loss: float
    action_mse: float


@dataclass(frozen=True)
class FrequencyConfig:
    """The four `FR-TRN-040` training frequencies, kept as four distinct meanings.

    Collapsing these into one "evaluation period" is exactly what `FR-TRN-040`
    forbids (CG-4C-06e). `eval_steps` is a held-out OFFLINE eval-loss cadence — an
    offline metric, not a selection basis — and `env_eval_freq` is a sim-rollout
    cadence unrelated to real-OpenArm success, which `meanings()` marks distinctly.

    Attributes:
        log_freq: Training-metric logging cadence, in steps.
        save_freq: Checkpoint-saving cadence, in steps.
        eval_steps: Held-out validation-loss cadence, in steps (offline metric).
        env_eval_freq: Sim-rollout evaluation cadence, in steps (unrelated to real
            OpenArm — `FR-TRN-040`).
    """

    log_freq: int
    save_freq: int
    eval_steps: int
    env_eval_freq: int

    def meanings(self) -> tuple[tuple[tuple[str, int, str], ...], str]:
        """Return the four frequencies with their distinct meanings and the env note.

        The renderer and CG-4C-06e both read this one source, so "the four are
        exposed distinctly" means one thing. The second element is the note that
        must accompany `env_eval_freq` specifically.

        Returns:
            (tuple) A 4-tuple of `(name, value, meaning)` in a fixed order, and the
                `env_eval_freq` "unrelated to real OpenArm" note.
        """
        rows = (
            (FREQ_LOG, self.log_freq, FREQ_MEANINGS[FREQ_LOG]),
            (FREQ_SAVE, self.save_freq, FREQ_MEANINGS[FREQ_SAVE]),
            (FREQ_EVAL_STEPS, self.eval_steps, FREQ_MEANINGS[FREQ_EVAL_STEPS]),
            (FREQ_ENV_EVAL, self.env_eval_freq, FREQ_MEANINGS[FREQ_ENV_EVAL]),
        )
        return rows, ENV_EVAL_FREQ_NOTE


@dataclass(frozen=True)
class PerTaskReport:
    """One (task, condition)'s success-rate report on this checkpoint.

    `condition` is a generic string value (`CONDITION_NOMINAL` /
    `CONDITION_PERTURBED`), joined by value rather than imported as WP-4C-05's enum
    (`02c` §3.6 DO-NOT-DUPLICATE).

    Attributes:
        task: The task the report is for.
        condition: The rollout condition, as a generic value.
        report: The WP-4C-03 `SuccessRateReport` for this (task, condition).
    """

    task: str
    condition: str
    report: SuccessRateReport


@dataclass(frozen=True)
class CheckpointScorecard:
    """One checkpoint's row in the checkpoint↔success-rate table (`02c` §3.6).

    Frozen: a scorecard is a computed summary keyed to an immutable checkpoint
    identity. The offline metrics are present for display and never for ranking;
    the generalization gap is derived and never given a confidence interval.

    Attributes:
        checkpoint: The WP-4A-05 lineage identity of the checkpoint.
        lineage_ref: The lineage reference the selection is attributable to (the
            handle a recorded selection decision is anchored by — `decision.py`).
        per_task: The per-(task, condition) success-rate reports.
        offline_metrics: Displayed, never ranked by (`FR-INF-062`).
        frequencies: The four `FR-TRN-040` frequencies as four meanings.
    """

    checkpoint: CheckpointId
    lineage_ref: str
    per_task: tuple[PerTaskReport, ...]
    offline_metrics: OfflineMetrics
    frequencies: FrequencyConfig

    @property
    def checkpoint_hash(self) -> str:
        """The `checkpoint_hash` the `02c` §3.6 contract names — the identity as text.

        Rendered identically to the WP-4C-03 report's `checkpoint_hash` so a
        scorecard and its reports agree on one checkpoint string.

        Returns:
            (str) `"<output_dir>@<step>"`.
        """
        return f"{self.checkpoint.output_dir}@{self.checkpoint.step}"

    @property
    def step(self) -> int:
        """The checkpoint step (`02c` §3.6 field `step`)."""
        return self.checkpoint.step

    def validate(self) -> None:
        """Enforce the structural invariants a selection row depends on.

        Raises:
            CheckpointScorecardError: On an empty `per_task`, a duplicated
                (task, condition), or an empty `lineage_ref`.
        """
        if not self.lineage_ref.strip():
            raise CheckpointScorecardError(
                f"lineage_ref must be non-empty for {self.checkpoint_hash}; a selection row must "
                "trace to WP-4A-05 lineage (FR-INF-062)"
            )
        if not self.per_task:
            raise CheckpointScorecardError(
                f"per_task is empty for {self.checkpoint_hash}; a scorecard row with no success "
                "rate is not a selection basis"
            )
        seen: set[tuple[str, str]] = set()
        for entry in self.per_task:
            key = (entry.task, entry.condition)
            if key in seen:
                raise CheckpointScorecardError(
                    f"duplicate (task, condition) {key} in {self.checkpoint_hash}; one report per "
                    "(task, condition)"
                )
            seen.add(key)
            # A scorecard is one checkpoint's row, so each report it carries must be
            # that checkpoint's — otherwise the table would pool a foreign checkpoint's
            # trials into this one's selection (compare_checkpoints refuses a mixed side).
            if entry.report.checkpoint != self.checkpoint:
                raise CheckpointScorecardError(
                    f"per_task report for {key} names checkpoint "
                    f"{entry.report.checkpoint_hash}, not the scorecard's {self.checkpoint_hash}"
                )

    def report_for(self, task: str, condition: str) -> SuccessRateReport | None:
        """Return the report for a (task, condition), or None when absent.

        Args:
            task: The task to look up.
            condition: The generic condition value to look up.

        Returns:
            (SuccessRateReport | None) The matching report, or None.
        """
        for entry in self.per_task:
            if entry.task == task and entry.condition == condition:
                return entry.report
        return None

    def tasks(self) -> tuple[str, ...]:
        """Return the distinct tasks on this scorecard, in first-seen order."""
        ordered: list[str] = []
        for entry in self.per_task:
            if entry.task not in ordered:
                ordered.append(entry.task)
        return tuple(ordered)

    def generalization_gap(self, task: str) -> float | None:
        """The DERIVED nominal−perturbed gap for a task, or None when unmeasured.

        `02c` §3.5: the gap is `nominal − perturbed` and nothing more — no separate
        confidence interval is claimed on it. With PERTURBED deferred until the
        Wave 3C distribution lands, the perturbed report is absent and the gap is
        `None`, which the renderer reports as "generalization gap unmeasured"; a
        `None` is never silently rendered as `0.0`.

        Args:
            task: The task to compute the gap for.

        Returns:
            (float | None) `nominal_point − perturbed_point`, or None when either
                condition's report is absent.
        """
        nominal = self.report_for(task, CONDITION_NOMINAL)
        perturbed = self.report_for(task, CONDITION_PERTURBED)
        if nominal is None or perturbed is None:
            return None
        return nominal.point_estimate - perturbed.point_estimate

    def render(self) -> str:
        """Render the scorecard row (`02c` §3.6 산출: 체크포인트↔성공률 표).

        The body is Korean because it is report content for the Korean planning
        corpus (the same split the WP-4C-03 renderer uses); this docstring stays
        English. Guarantees the acceptance gates read:

        - the robomimic warning is stamped first, unconditionally (CG-4C-06b);
        - every per-task report carries its Wilson CI (delegated to WP-4C-03);
        - the offline metrics are shown and marked display-only (CG-4C-06a intent);
        - the four frequencies are shown with four meanings and the env note
          (CG-4C-06e);
        - the generalization gap is derived, or stated unmeasured (`02c` §3.5).

        Returns:
            (str) The rendered scorecard.
        """
        lines = [
            ROBOMIMIC_WARNING,
            "",
            "체크포인트 스코어카드",
            f"체크포인트: {self.checkpoint_hash}",
            f"스텝: {self.step}",
            f"계보 참조: {self.lineage_ref}",
            "",
            "태스크별 성공률 (조건 분리):",
        ]
        for entry in self.per_task:
            report = entry.report
            wilson = report.ci_wilson_95
            lines.append(
                f"  [{entry.task} / {entry.condition}] "
                f"성공률 {report.point_estimate:.4f} "
                f"Wilson95 [{wilson.lower:.4f}, {wilson.upper:.4f}] (N={report.n_trials})"
            )
        lines.append("")
        lines.append("일반화 격차 (파생값, 별도 CI 없음):")
        for task in self.tasks():
            gap = self.generalization_gap(task)
            if gap is None:
                lines.append(f"  [{task}] {GENERALIZATION_GAP_UNMEASURED}")
            else:
                lines.append(f"  [{task}] nominal − perturbed = {gap:+.4f}")
        lines.append("")
        lines.append(f"오프라인 지표 ({OFFLINE_METRICS_DISPLAY_ONLY}):")
        lines.append(f"  val_loss = {self.offline_metrics.val_loss:.6f}")
        lines.append(f"  action_mse = {self.offline_metrics.action_mse:.6f}")
        lines.append("")
        lines.append("학습 주기 (4개 별개 의미 — FR-TRN-040):")
        rows, env_note = self.frequencies.meanings()
        for name, value, meaning in rows:
            lines.append(f"  {name} = {value}: {meaning}")
        lines.append(f"  └ {FREQ_ENV_EVAL}: {env_note}")
        return "\n".join(lines)
