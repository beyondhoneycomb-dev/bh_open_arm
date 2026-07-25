"""The per-condition report axis (`02c` §3.5 산출: 조건별 리포트 축) and its renderer.

The report shows the two conditions separately (CG-4C-05b), states the generalization
gap as a DERIVED scalar with an explicit note that it carries no separate confidence
interval (CG-4C-05b ②), states the exact "일반화 격차 미측정" phrase when the perturbed
condition is deferred (CG-4C-05c), and always states the PERTURBED reproducibility
limit (CG-4C-05e) — the trade-off the plan refuses to hide.

Two invariants are structural, not by convention:

- **No gap confidence interval.** `generalization_gap` is a `float | None` and nothing
  else; there is no field, and no render line, that attaches an interval to the gap.
- **Deferral is stated, never silent.** When the perturbed arm is absent the report
  carries the perturbation protocol's `deferred_reason` (which names the missing Wave 3C
  distribution) and the unmeasured-gap phrase, so a report that could not measure the
  gap says so on its face.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.eval.protocol.constants import (
    GAP_DERIVED_NO_CI_NOTE,
    GENERALIZATION_GAP_UNMEASURED,
    NOMINAL_SECTION_LABEL,
    PERTURBED_REPRODUCIBILITY_LIMIT,
    PERTURBED_SECTION_LABEL,
    REPORT_TITLE,
)
from backend.eval.protocol.dual_condition import ConditionArm, DualConditionSet


@dataclass(frozen=True)
class DualConditionReport:
    """The report axis for one dual-condition set — both conditions and the derived gap.

    Frozen: a report is a computed view of a fixed `DualConditionSet`. Every field the
    contract needs is present; `generalization_gap` is a scalar difference and there is
    deliberately no companion interval field for it (CG-4C-05b).

    Attributes:
        checkpoint_hash: The shared checkpoint hash both conditions were run on.
        success_criterion_id: The shared success criterion both conditions were judged by.
        n_trials: The shared trial count per condition.
        nominal: The NOMINAL condition arm.
        perturbed: The PERTURBED condition arm, or `None` when deferred.
        generalization_gap: The DERIVED gap `nominal - perturbed`, or `None` when the
            perturbed condition is absent. A plain scalar; never carries a CI.
        gap_measured: Whether the gap is measured (the perturbed arm is present).
        perturbation_deferred_reason: The protocol's deferral reason when the perturbed
            arm is absent (names the missing Wave 3C distribution); empty when measured.
        reproducibility_limit: The PERTURBED reproducibility limit, always stated.
    """

    checkpoint_hash: str
    success_criterion_id: str
    n_trials: int
    nominal: ConditionArm
    perturbed: ConditionArm | None
    generalization_gap: float | None
    gap_measured: bool
    perturbation_deferred_reason: str
    reproducibility_limit: str

    @staticmethod
    def of(dual_set: DualConditionSet) -> DualConditionReport:
        """Build the report axis from a validated dual-condition set.

        Args:
            dual_set: The set to report on.

        Returns:
            (DualConditionReport) The report, with the gap derived from the set.
        """
        deferred_reason = (
            "" if dual_set.perturbed is not None else dual_set.perturbation.deferred_reason
        )
        return DualConditionReport(
            checkpoint_hash=dual_set.nominal.checkpoint_hash,
            success_criterion_id=dual_set.nominal.success_criterion_id,
            n_trials=dual_set.nominal.n_trials,
            nominal=dual_set.nominal,
            perturbed=dual_set.perturbed,
            generalization_gap=dual_set.generalization_gap,
            gap_measured=dual_set.is_gap_measured,
            perturbation_deferred_reason=deferred_reason,
            reproducibility_limit=PERTURBED_REPRODUCIBILITY_LIMIT,
        )

    def render(self) -> str:
        """Render the human-readable per-condition report (`02c` §3.5 산출).

        The body is Korean, matching the WP-4C-03 renderer and the planning corpus it
        joins; this docstring stays English. Guarantees the acceptance gates read:

        - both conditions appear as separate sections (CG-4C-05b);
        - the gap is shown as a derived scalar with the no-CI note, or as the exact
          unmeasured phrase when deferred (CG-4C-05b/c);
        - the deferral reason names the missing Wave 3C distribution (CG-4C-05c);
        - both conditions' seeds are printed (CG-4C-05d);
        - the PERTURBED reproducibility limit is always present (CG-4C-05e).

        Returns:
            (str) The rendered report.
        """
        lines = [
            REPORT_TITLE,
            f"체크포인트 해시: {self.checkpoint_hash}",
            f"성공 기준 ID: {self.success_criterion_id}",
            f"조건당 시행 수 N: {self.n_trials}",
            "",
            *_render_arm(NOMINAL_SECTION_LABEL, self.nominal),
            "",
        ]
        if self.perturbed is not None:
            lines.extend(_render_arm(PERTURBED_SECTION_LABEL, self.perturbed))
            lines.append("")
            gap = self.generalization_gap if self.generalization_gap is not None else 0.0
            lines.append(f"일반화 격차(파생) = nominal - perturbed = {gap:+.4f}")
            lines.append(GAP_DERIVED_NO_CI_NOTE)
        else:
            lines.append(f"{PERTURBED_SECTION_LABEL}: {GENERALIZATION_GAP_UNMEASURED}")
            lines.append(self.perturbation_deferred_reason)
        lines.append("")
        lines.append(self.reproducibility_limit)
        return "\n".join(lines)


def _render_arm(label: str, arm: ConditionArm) -> list[str]:
    """Render one condition arm as its own section, seeds included (CG-4C-05b/d)."""
    wilson = arm.report.ci_wilson_95
    return [
        f"[{label}]",
        f"점추정 성공률: {arm.point_estimate:.4f}",
        f"Wilson 95% CI: [{wilson.lower:.4f}, {wilson.upper:.4f}]",
        f"시행 수 N: {arm.n_trials}",
        f"시드: {list(arm.seeds)}",
    ]
