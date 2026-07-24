"""WP-4A-03 — the degenerate-channel detector (`02c` §1.3).

With `use_velocity_and_torque=True` the observation vector carries `.vel` (deg/s)
and `.torque` (Nm). A STATIONARY joint's `.vel` is a constant 0 and a NON-CONTACT
span's `.torque` is near-constant — both give a per-channel statistic ~ 0. LeRobot's
`normalize_processor` then divides by `denom = statistic + eps` (eps=1e-8, floored;
the N-1 ledger resolution — `10` FR-TRN-067 wins, the floor IS applied and its
being applied is the cause, superseding `08` §2.6.1's `[미확인]`), so the channel's
residual noise is amplified ~1e6 and dominates the loss. No exception, no stack
trace: the run finishes and only a bad policy comes out.

This band DETECTS and EXPOSES that; it cannot FIX it. Element-wise normalization is
LeRobot's contract and `FR-TRN-069` forbids the per-group rescaling that would
otherwise rescue a mixed-unit channel, so channel EXCLUDE is the only remedy — a
structural limit set by the normalization contract, not by our choice.

What it provides:

- `detector` — per-mode detection (MEAN_STD by std, MIN_MAX by max−min, QUANTILES
  by q99−q01), located by channel NAME so a rotated names order still names the same
  channel (`FR-TRN-063` discipline), with an amplification estimate;
- `harness` — the σ_min/δ_min DERIVATION harness: a channel-statistic histogram that
  yields a threshold at the cluster valley WITH its rationale, or declines and defers
  to showing every channel. It never hard-codes σ_min (`02c` §1.3 σ_min block) and is
  flagged for re-run on Wave 3C real data;
- `gate` — the capability-token gate that forbids a training clearance while any
  finding is undecided (`FR-TRN-068`, `CG-4A-03d`);
- `lineage` — the immutable `FR-TRN-054` (h) slice, making the three-way decision
  queryable (`CG-4A-03e`).
"""

from __future__ import annotations

from backend.training.degenerate.detector import (
    amplification_estimate,
    channel_statistic,
    channel_statistics,
    detect_degenerate_channels,
    detect_in_observation_state,
)
from backend.training.degenerate.finding import (
    DegenerateChoice,
    DegenerateDecision,
    DegenerateFinding,
    NormMode,
)
from backend.training.degenerate.gate import (
    DegenerateGateError,
    TrainingClearance,
    clear_for_training,
    present_choices,
    undecided_findings,
)
from backend.training.degenerate.harness import ThresholdDerivation, derive_threshold
from backend.training.degenerate.lineage import DegenerateLineageStore

__all__ = [
    "DegenerateChoice",
    "DegenerateDecision",
    "DegenerateFinding",
    "DegenerateGateError",
    "DegenerateLineageStore",
    "NormMode",
    "ThresholdDerivation",
    "TrainingClearance",
    "amplification_estimate",
    "channel_statistic",
    "channel_statistics",
    "clear_for_training",
    "derive_threshold",
    "detect_degenerate_channels",
    "detect_in_observation_state",
    "present_choices",
    "undecided_findings",
]
