"""WP-4A-06 — the `.pos` subvector selector and paired ablation infra (`02c` §1.6).

The experiment infrastructure for the torque/velocity contribution study
(`10` FR-TRN-073/074, `11` FR-INF-074). It builds the two things §1.6 names:

- `select_pos_indices(names)` — the name-derived `.pos` index extractor for both
  the observation and the action vectors, never a positional slice (the FR-TRN-063
  trap); and
- `generate_paired_experiment(...)` — the twin-job generator that pins the four
  FR-TRN-073 controls as types so the two arms cannot differ except in projection.

The action target is position-only in both arms; `select_action_target_indices`
and the static `scan_package` are the runtime and static halves of "no
`.vel`/`.torque` reaches the action target". This WP builds the infra only — the
conclusion of the ablation is 4C's (`02c` §1.6 workflow). It consumes the committed
WP-4A-02 `ObservationConfig` and the frozen `CTR-REC@v1` / `CTR-ACT@v1` schemas by
import; it redefines no contract.
"""

from __future__ import annotations

from backend.training.projection.check import (
    PROJECTION_PACKAGE_ROOT,
    scan_package,
    scan_source,
)
from backend.training.projection.experiment import (
    ArmRequest,
    ExperimentArm,
    PairedExperiment,
    PairedExperimentError,
    generate_paired_experiment,
)
from backend.training.projection.selector import (
    ACTION_TARGET_FORBIDDEN_SUFFIXES,
    ActionTargetLeakError,
    ProjectionKind,
    observation_projection_indices,
    select_action_target_indices,
    select_pos_indices,
)

__all__ = [
    "ACTION_TARGET_FORBIDDEN_SUFFIXES",
    "PROJECTION_PACKAGE_ROOT",
    "ActionTargetLeakError",
    "ArmRequest",
    "ExperimentArm",
    "PairedExperiment",
    "PairedExperimentError",
    "ProjectionKind",
    "generate_paired_experiment",
    "observation_projection_indices",
    "scan_package",
    "scan_source",
    "select_action_target_indices",
    "select_pos_indices",
]
