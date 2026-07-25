"""The dual-condition set: two conditions bound under one controlled comparison.

`02c` §3.5 CG-4C-05a is the load-bearing invariant: a NOMINAL and a PERTURBED rollout
set must share the same checkpoint hash, the same trial count, and the same
success-criterion id, or the set is refused. Without that, the two success rates are
not measured under a controlled comparison and their difference is not a
generalization gap — it is a confound. So `DualConditionSet.create` refuses the set on
any mismatch, and the refusal is the product, not a warning.

The generalization gap is a DERIVED scalar — `nominal - perturbed` — exposed as a
property, never stored beside a confidence interval. CG-4C-05b forbids asserting a CI
on the gap (a difference-of-two-binomials CI is a statistic the spec grounds nowhere),
so there is deliberately no field and no method here that returns an interval for the
gap; the gap is a plain `float | None`, `None` when the perturbed condition is absent.

This module consumes the committed WP-4C-03 aggregator directly: `aggregate_condition`
calls `backend.eval.stats.aggregate` to turn a condition's episodes into the
`SuccessRateReport` a `ConditionArm` wraps. That import is also what backs the declared
WP-4C-03 -> WP-4C-05 downstream edge in the reference graph (`06` §5.6 / CI-16); the
edge is a real static reference, not a phantom. The real rollout population is DEFERRED
(WP-4C-01/02, Human/HW), so the reports are aggregated from synthetic episodes here and
in tests — never a fabricated rollout number.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.eval.protocol.condition import Condition
from backend.eval.protocol.perturbation import PerturbationProtocol

# WP-4C-03 aggregator consumption: `aggregate` builds the SuccessRateReport a condition
# arm wraps, and `SuccessRateReport` is the report type it carries. This is the
# committed contract, imported and not redefined (`02c` DO-NOT-DUPLICATE).
from backend.eval.stats import EpisodeRecord, SuccessRateReport, aggregate

# WP-4A-05 lineage consumption: a report is aggregated FOR a lineage checkpoint identity,
# which `aggregate_condition` passes straight through to the WP-4C-03 aggregator.
from backend.training.lineage import CheckpointId


class ConditionSetError(ValueError):
    """Raised when a condition arm or dual-condition set violates its schema.

    The cases: an arm whose condition does not match its slot (a PERTURBED arm in the
    nominal slot, or vice versa), an arm with a blank success-criterion id or no
    recorded seeds (CG-4C-05d), a perturbed arm reported under a deferred perturbation
    protocol, or a NOMINAL/PERTURBED pair that disagrees on checkpoint hash, trial
    count, or success-criterion id (CG-4C-05a).
    """


@dataclass(frozen=True)
class ConditionArm:
    """One condition's aggregated outcome: its `SuccessRateReport` plus its identity.

    Frozen because an arm is a recorded summary of a fixed rollout set. The report
    carries the checkpoint identity, the trial count, the seeds, the point estimate and
    the Wilson interval; this arm adds only the two things the report does not name —
    which `Condition` produced it, and which success criterion it was judged by
    (`FR-TRN-073` (d)).

    Attributes:
        condition: The condition this arm was run under.
        report: The committed WP-4C-03 `SuccessRateReport` for this arm.
        success_criterion_id: The success criterion the episodes were judged by.
    """

    condition: Condition
    report: SuccessRateReport
    success_criterion_id: str

    def __post_init__(self) -> None:
        """Refuse an arm with no criterion or no recorded seeds (CG-4C-05d).

        Raises:
            ConditionSetError: When `success_criterion_id` is blank, or the report
                records no per-episode seeds (`FR-SIM-056` reproducibility).
        """
        if not self.success_criterion_id.strip():
            raise ConditionSetError(
                "a condition arm must name its success criterion (FR-TRN-073 d)"
            )
        if not self.report.seeds:
            raise ConditionSetError(
                "a condition arm must record its per-episode initial-state seeds "
                "(FR-SIM-056 / CG-4C-05d); both conditions record seeds"
            )

    @property
    def checkpoint_hash(self) -> str:
        """The evaluated checkpoint's hash, from the wrapped report."""
        return self.report.checkpoint_hash

    @property
    def n_trials(self) -> int:
        """The trial count, from the wrapped report."""
        return self.report.n_trials

    @property
    def point_estimate(self) -> float:
        """The point-estimate success rate, from the wrapped report."""
        return self.report.point_estimate

    @property
    def seeds(self) -> tuple[int, ...]:
        """The per-episode initial-state seeds, from the wrapped report (CG-4C-05d)."""
        return self.report.seeds


def aggregate_condition(
    condition: Condition,
    rollout_set_id: str,
    checkpoint: CheckpointId,
    episodes: Sequence[EpisodeRecord],
    success_criterion_id: str,
) -> ConditionArm:
    """Aggregate one condition's episodes into a `ConditionArm` via the WP-4C-03 aggregator.

    This is the single consumption point of `backend.eval.stats.aggregate`: the dual
    condition protocol never re-implements the success-rate math, it delegates to the
    committed aggregator and wraps the result with the condition and success criterion.

    Args:
        condition: The condition these episodes were run under.
        rollout_set_id: The rollout set the episodes belong to.
        checkpoint: The WP-4A-05 lineage identity of the evaluated checkpoint.
        episodes: The episodes to aggregate; must be non-empty and each valid.
        success_criterion_id: The success criterion the episodes were judged by.

    Returns:
        (ConditionArm) The condition arm wrapping the aggregated report.

    Raises:
        AggregationError: When `episodes` is empty (from the WP-4C-03 aggregator).
        ConditionSetError: When the criterion is blank or the report records no seeds.
    """
    report = aggregate(rollout_set_id, checkpoint, episodes)
    return ConditionArm(
        condition=condition, report=report, success_criterion_id=success_criterion_id
    )


@dataclass(frozen=True)
class DualConditionSet:
    """A NOMINAL arm, an optional PERTURBED arm, and the perturbation protocol.

    Built through `create`, which enforces the CG-4C-05a invariant so an ill-formed set
    is never representable. The generalization gap is derived here, never stored, and
    never carries a confidence interval (CG-4C-05b).

    Attributes:
        nominal: The NOMINAL condition arm (always present).
        perturbed: The PERTURBED condition arm, or `None` when perturbed is deferred —
            the phase-1 state, since the Wave 3C distribution has not landed.
        perturbation: The perturbation protocol; deferred iff `perturbed` is `None`.
    """

    nominal: ConditionArm
    perturbed: ConditionArm | None
    perturbation: PerturbationProtocol

    @staticmethod
    def create(
        nominal: ConditionArm,
        perturbed: ConditionArm | None,
        perturbation: PerturbationProtocol,
    ) -> DualConditionSet:
        """Build a dual-condition set, refusing any CG-4C-05a mismatch.

        Args:
            nominal: The NOMINAL arm; its condition must be `Condition.NOMINAL`.
            perturbed: The PERTURBED arm, or `None` for the NOMINAL-only deferred path.
            perturbation: The perturbation protocol. Must be deferred when `perturbed`
                is `None`, and defined when `perturbed` is present — a measured perturbed
                arm requires a Wave-3C-derived protocol behind it (CG-4C-05c).

        Returns:
            (DualConditionSet) The validated set.

        Raises:
            ConditionSetError: When an arm sits in the wrong condition slot, when a
                perturbed arm is reported under a deferred protocol, or when the two
                arms disagree on checkpoint hash, trial count, or success-criterion id.
        """
        if nominal.condition is not Condition.NOMINAL:
            raise ConditionSetError(
                f"the nominal slot must carry a NOMINAL arm, got {nominal.condition.value}"
            )
        if perturbed is None:
            return DualConditionSet(nominal=nominal, perturbed=None, perturbation=perturbation)

        if perturbed.condition is not Condition.PERTURBED:
            raise ConditionSetError(
                f"the perturbed slot must carry a PERTURBED arm, got {perturbed.condition.value}"
            )
        if perturbation.is_deferred:
            raise ConditionSetError(
                "a PERTURBED arm cannot be reported under a deferred perturbation protocol; the "
                "protocol must define its Wave-3C-derived axes before the condition is run "
                "(CG-4C-05c)"
            )
        _refuse_on_mismatch(nominal, perturbed)
        return DualConditionSet(nominal=nominal, perturbed=perturbed, perturbation=perturbation)

    @property
    def is_gap_measured(self) -> bool:
        """Whether the generalization gap is measurable (the perturbed arm is present)."""
        return self.perturbed is not None

    @property
    def generalization_gap(self) -> float | None:
        """The DERIVED generalization gap `nominal - perturbed`, or `None` when unmeasured.

        A plain scalar difference of the two point estimates (`02c` §3.5 ②). It is
        `None`, not zero, when the perturbed condition is absent — an unmeasured gap is
        not a gap of nothing. No confidence interval is attached to it, by contract.

        Returns:
            (float | None) `nominal.point_estimate - perturbed.point_estimate`, or `None`.
        """
        if self.perturbed is None:
            return None
        return self.nominal.point_estimate - self.perturbed.point_estimate


def _refuse_on_mismatch(nominal: ConditionArm, perturbed: ConditionArm) -> None:
    """Refuse a NOMINAL/PERTURBED pair that is not a controlled comparison (CG-4C-05a).

    The three axes `FR-TRN-073` (c)/(d) fixes must match exactly: same checkpoint hash,
    same trial count, same success-criterion id. Any one mismatch makes the gap a
    confound rather than a measurement, so the set is refused rather than reported.

    Raises:
        ConditionSetError: On any of the three mismatches.
    """
    if nominal.checkpoint_hash != perturbed.checkpoint_hash:
        raise ConditionSetError(
            "NOMINAL and PERTURBED must share one checkpoint hash (CG-4C-05a); got "
            f"{nominal.checkpoint_hash!r} vs {perturbed.checkpoint_hash!r}"
        )
    if nominal.n_trials != perturbed.n_trials:
        raise ConditionSetError(
            "NOMINAL and PERTURBED must share one trial count (CG-4C-05a); got "
            f"{nominal.n_trials} vs {perturbed.n_trials}"
        )
    if nominal.success_criterion_id != perturbed.success_criterion_id:
        raise ConditionSetError(
            "NOMINAL and PERTURBED must share one success-criterion id (CG-4C-05a); got "
            f"{nominal.success_criterion_id!r} vs {perturbed.success_criterion_id!r}"
        )
