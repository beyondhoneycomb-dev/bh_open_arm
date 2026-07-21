"""WP-0C-07 — learning/eval statistics on a synthetic 48-dim dataset.

This band is AI-offline and CAN-free (SPINE §5): every deliverable here runs on a
synthetic dataset that is byte-for-byte the real LeRobot v3.0 schema (`09`
FR-SIM-020 spirit), so the learning and evaluation statistics can be validated
before any hardware or vcan device exists.

Four deliverables, one per module:

- `synthetic_dataset`  — a generator that writes a real LeRobot v3.0 dataset whose
  `observation.state` is the 48-dim bimanual vector and whose `action` is
  position-only (`10` FR-TRN-074).
- `channel_groups` / `normalization_stats` — normalization statistics computed
  per unit-tag channel group (deg / deg-per-sec / Nm), never one statistic over
  the mixed vector (`16` D-8).
- `policy_constraints` — the FR-TRN-017 structural pre-validator, each of its six
  conditions blocked under its own distinct code.
- `success_rate` — a success-rate aggregator with Wilson and Clopper-Pearson
  confidence intervals (`14` FR-OPS-086).
"""

from __future__ import annotations

from backend.learning.channel_groups import (
    StateChannel,
    group_indices_by_unit,
    state_channels,
)
from backend.learning.normalization_stats import (
    ChannelGroupStats,
    MixedUnitStatWarning,
    compute_channel_group_stats,
    pooled_stats_over_vector,
)
from backend.learning.policy_constraints import (
    DatasetProfile,
    PolicyConstraintCode,
    PolicySpec,
    PolicyStructuralValidator,
    Violation,
)
from backend.learning.provenance import build_provenance_manifest
from backend.learning.success_rate import (
    ConfidenceInterval,
    SuccessRate,
    SuccessRateAggregator,
    clopper_pearson_interval,
    wilson_interval,
)
from backend.learning.synthetic_dataset import (
    SyntheticDatasetSpec,
    build_synthetic_dataset,
    state_action_feature_spec,
)

__all__ = [
    "ChannelGroupStats",
    "ConfidenceInterval",
    "DatasetProfile",
    "MixedUnitStatWarning",
    "PolicyConstraintCode",
    "PolicySpec",
    "PolicyStructuralValidator",
    "StateChannel",
    "SuccessRate",
    "SuccessRateAggregator",
    "SyntheticDatasetSpec",
    "Violation",
    "build_provenance_manifest",
    "build_synthetic_dataset",
    "clopper_pearson_interval",
    "compute_channel_group_stats",
    "group_indices_by_unit",
    "pooled_stats_over_vector",
    "state_action_feature_spec",
    "state_channels",
    "wilson_interval",
]
