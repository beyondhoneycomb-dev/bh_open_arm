"""WP-4A-02 — the dataset preflight checker (`02c` §1.2).

The offline gate a dataset/policy pair passes before `lerobot-train` starts. It
judges an observation configuration by its `names` (the canonical authority,
`10` FR-TRN-061), verifies the per-motor `names` order the trainer indexes by
(`FR-TRN-063`), refuses to promote a structural-exclusion meta feature into the
policy namespace (`FR-TRN-076`), and blocks a quantile-normalized policy paired
with statistics missing `q01`/`q99` (`FR-TRN-020`, `08` FR-DAT-026) — suggesting
the augment script rather than silently running it.

`preflight(dataset, policy) -> PreflightReport` is the entry point; the LeRobot
`dataset_to_policy_features` classifier and the frozen `CTR-REC@v1` name grammar
are consumed by import, never reimplemented.
"""

from __future__ import annotations

from backend.training.preflight.checker import DatasetPreflightInput, preflight
from backend.training.preflight.observation import (
    ObservationConfig,
    derive_observation_config,
    split_channel,
)
from backend.training.preflight.policy import (
    AUGMENT_SCRIPT,
    QUANTILE_MODES,
    REQUIRED_QUANTILE_KEYS,
    PolicyPreflightSpec,
)
from backend.training.preflight.report import (
    Component,
    PreflightCode,
    PreflightFinding,
    PreflightReport,
    Verdict,
)

__all__ = [
    "AUGMENT_SCRIPT",
    "QUANTILE_MODES",
    "REQUIRED_QUANTILE_KEYS",
    "Component",
    "DatasetPreflightInput",
    "ObservationConfig",
    "PolicyPreflightSpec",
    "PreflightCode",
    "PreflightFinding",
    "PreflightReport",
    "Verdict",
    "derive_observation_config",
    "preflight",
    "split_channel",
]
