"""The policy half of a preflight: how a policy normalizes and remaps a dataset.

Preflight judges a policy by its declared behaviour, not its name — the same
discipline `10` FR-TRN-061 applies to datasets. Whether `q01`/`q99` are required
is read from the policy's `normalization_mapping` (a QUANTILES/QUANTILE10 mode for
a present feature type), not from a hard-coded list of policy names, so a policy
that switches its normalization mode is judged by what it will actually do.

The `rename_map` and `input_features` this spec carries are the training-config
knobs that adapt a dataset to a policy (`lerobot.configs.train.TrainPipelineConfig.
rename_map`). They belong to this side because they describe how the policy
consumes the dataset — a rename that rotates channel order or promotes a
structural-exclusion feature is a property of the pairing, not of the recording.

`NormalizationMode` is imported from LeRobot so the mode strings cannot drift from
the enum the training normalizer keys on.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from lerobot.configs.types import NormalizationMode

# The normalization modes that consume quantile statistics. `QUANTILES` uses
# `q01`/`q99` and `QUANTILE10` uses `q10`/`q90`; either makes the quantile keys
# non-optional (`08` FR-DAT-026, `10` FR-TRN-020). Read from the LeRobot enum so
# a new quantile mode there is caught here rather than silently unhandled.
QUANTILE_MODES: frozenset[str] = frozenset(
    {NormalizationMode.QUANTILES.value, NormalizationMode.QUANTILE10.value}
)

# The two quantile keys `pi0.5` reads for a QUANTILES-normalized feature (`08` §8.2
# WP-3D-03: q01/q99 are not optional). The augment script recomputes the full set.
REQUIRED_QUANTILE_KEYS: tuple[str, ...] = ("q01", "q99")

# The remediation for missing quantile statistics — SUGGESTED, never auto-run:
# augmenting rewrites `meta/stats.json` and so silently changes the stats content
# hash, which would stale every checkpoint trained on the old hash (`02c` §0.4,
# §1.2 negative branch ③). The user must run it deliberately.
AUGMENT_SCRIPT = "lerobot/scripts/augment_dataset_quantile_stats.py"


@dataclass(frozen=True)
class PolicyPreflightSpec:
    """The policy configuration a dataset is preflighted against.

    Only the fields preflight reads are modelled; a real policy config carries far
    more. Named distinctly from `backend.learning.policy_constraints.PolicySpec`,
    which models the six FR-TRN-017 structural constraints — a different concern.

    Attributes:
        name: The policy identifier, for finding messages only (never the judgment
            basis).
        normalization_modes: Feature-type name (`STATE`/`ACTION`/`VISUAL`) to its
            `NormalizationMode` value. The authority for whether quantiles are
            required.
        rename_map: Dataset-key/channel-name remaps the training config applies
            before the policy reads the dataset; empty when the dataset is
            consumed as recorded.
        input_features: Feature keys the policy explicitly requests as inputs
            beyond the dataset defaults; a structural-exclusion key here is a
            direct promotion (`10` FR-TRN-076).
    """

    name: str
    normalization_modes: Mapping[str, str]
    rename_map: Mapping[str, str] = field(default_factory=dict)
    input_features: tuple[str, ...] = ()

    def requires_quantiles(self) -> bool:
        """Whether any declared normalization mode consumes quantile statistics.

        Returns:
            (bool) True iff a feature type is normalized by QUANTILES/QUANTILE10.
        """
        return any(mode in QUANTILE_MODES for mode in self.normalization_modes.values())

    def normalization_of(self, feature_type: str) -> str | None:
        """Return the normalization mode for a feature type, or None when unset.

        Args:
            feature_type: A `FeatureType` value such as `STATE`.

        Returns:
            (str | None) The mode value, or None when the policy declares none.
        """
        return self.normalization_modes.get(feature_type)

    @classmethod
    def from_lerobot_config(
        cls,
        name: str,
        config: Any,
        rename_map: Mapping[str, str] | None = None,
        input_features: tuple[str, ...] = (),
    ) -> PolicyPreflightSpec:
        """Build a spec from an installed LeRobot policy config's normalization map.

        This grounds the quantile judgment in the real policy config rather than a
        name table: `PI05Config().normalization_mapping` maps STATE and ACTION to
        QUANTILES, so a pi0.5 spec built this way requires quantiles because the
        installed config says so.

        Args:
            name: The policy identifier for messages.
            config: A LeRobot policy config carrying `normalization_mapping`.
            rename_map: The training config's rename map, if any.
            input_features: Explicitly requested policy input feature keys.

        Returns:
            (PolicyPreflightSpec) A spec mirroring the config's normalization map.
        """
        mapping = getattr(config, "normalization_mapping", {}) or {}
        modes = {
            (feature_type.value if hasattr(feature_type, "value") else str(feature_type)): (
                mode.value if hasattr(mode, "value") else str(mode)
            )
            for feature_type, mode in mapping.items()
        }
        return cls(
            name=name,
            normalization_modes=modes,
            rename_map=dict(rename_map or {}),
            input_features=tuple(input_features),
        )
