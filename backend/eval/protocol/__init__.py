"""WP-4C-05 phase-1 — the nominal + perturbed dual-condition protocol (`02c` §3.5).

The AI-offline half of the dual-condition protocol: the condition-definition schema,
the perturbation-protocol structure, and the per-condition report axis. It enforces the
protocol's load-bearing invariants in code rather than by convention, and it never fakes
a rollout number — the perturbation execution and human judgment are DEFERRED (Human/HW).

- **Two conditions, no third.** `Condition ∈ {NOMINAL, PERTURBED}`, owned here; downstream
  reads the value by string, not by importing the enum (`condition`).
- **Same checkpoint, trials, criterion — or refused.** `DualConditionSet.create` refuses a
  NOMINAL/PERTURBED pair that disagrees on any of the three (`dual_condition`, CG-4C-05a).
- **Gap is derived, never given a CI.** `generalization_gap` is a `float | None` scalar;
  no field or method attaches an interval to it (`dual_condition`/`report`, CG-4C-05b).
- **Axes reference Wave 3C; deferral is stated.** A `PerturbationAxis` cannot exist without
  its Wave 3C reference, and because that distribution has not landed the only protocol
  this phase produces is the deferred one, whose report states the gap is unmeasured
  (`perturbation`/`report`, CG-4C-05c).
- **Seeds recorded, reproducibility limit stated.** Every arm records its seeds
  (CG-4C-05d) and every report states the PERTURBED reproducibility limit (CG-4C-05e).

It consumes the committed WP-4C-03 aggregator (`backend.eval.stats.aggregate`) and the
WP-4A-05 lineage checkpoint identity; it redefines neither.
"""

from __future__ import annotations

from backend.eval.protocol.condition import Condition
from backend.eval.protocol.constants import (
    GENERALIZATION_GAP_UNMEASURED,
    PERTURBED_DEFERRED_REASON,
    PERTURBED_REPRODUCIBILITY_LIMIT,
    WAVE_3C_DISTRIBUTION_REF,
)
from backend.eval.protocol.dual_condition import (
    ConditionArm,
    ConditionSetError,
    DualConditionSet,
    aggregate_condition,
)
from backend.eval.protocol.perturbation import (
    PerturbationAxis,
    PerturbationError,
    PerturbationProtocol,
)
from backend.eval.protocol.report import DualConditionReport

__all__ = [
    "GENERALIZATION_GAP_UNMEASURED",
    "PERTURBED_DEFERRED_REASON",
    "PERTURBED_REPRODUCIBILITY_LIMIT",
    "WAVE_3C_DISTRIBUTION_REF",
    "Condition",
    "ConditionArm",
    "ConditionSetError",
    "DualConditionReport",
    "DualConditionSet",
    "PerturbationAxis",
    "PerturbationError",
    "PerturbationProtocol",
    "aggregate_condition",
]
