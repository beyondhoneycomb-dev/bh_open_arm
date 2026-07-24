"""Fault-injection fixtures for the WP-4A-02 preflight — the second SHAPE-IM builder.

`02c` §1.2 workflow SHAPE-IM(2): the checker and this fixture generator define each
other's failure. Every fault case here starts from the COMMITTED synthetic 48-dim
dataset (`contracts.fixtures.synthetic_dataset.build_synthetic_dataset`) and the
frozen metric-key set (`backend.dataset.stats.constants.METRIC_KEYS`) — consumed by
reference, never re-spelt — and injects exactly one defect. A case is only useful
if it makes the checker BLOCK; a clean pair is only useful if the checker PASSes it
with an empty findings set. If a fault fixture fails to fire, the fixture is weak;
if a passing gate could be built from a fixture, the checker is weak (`02c` §0.5).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.dataset.stats.constants import METRIC_KEYS
from backend.training.preflight import (
    DatasetPreflightInput,
    PolicyPreflightSpec,
    PreflightCode,
)
from contracts.fixtures.synthetic_dataset import build_synthetic_dataset
from contracts.recorder import (
    OBSERVATION_STATE_KEY,
    TORQUE_SUFFIX,
    observation_state_names,
)

# The two structural-exclusion feature keys a promotion fault targets. `timestamp`
# is the one `02c` §1.2 ④ names explicitly; the others share the exclusion
# (`10` FR-TRN-076, D-7).
TIMESTAMP_META_KEY = "timestamp"

# pi0.5's normalization mapping, mirrored from the installed `PI05Config`
# (STATE/ACTION -> QUANTILES, VISUAL -> IDENTITY). Built directly so the gate tests
# stay hermetic; `test_policy_spec.py` grounds this against the real config.
PI05_NORMALIZATION = {"STATE": "QUANTILES", "ACTION": "QUANTILES", "VISUAL": "IDENTITY"}
# smolvla normalizes STATE/ACTION with MEAN_STD, so it needs no quantile stats — the
# negative control that proves the quantile gate keys on the mode, not the dataset.
SMOLVLA_NORMALIZATION = {"STATE": "MEAN_STD", "ACTION": "MEAN_STD", "VISUAL": "IDENTITY"}


@dataclass(frozen=True)
class FaultCase:
    """One fault-injection case and the verdict it must provoke.

    Attributes:
        gate_id: The `02c` §1.2 acceptance check this case exercises.
        dataset: The (possibly faulted) dataset input.
        policy: The policy the dataset is paired with.
        expected_code: The fault code the checker must raise.
    """

    gate_id: str
    dataset: DatasetPreflightInput
    policy: PolicyPreflightSpec
    expected_code: PreflightCode


def _clean_info() -> dict[str, dict[str, object]]:
    """Return a mutable copy of the committed fixture's `info.json` feature map."""
    dataset = build_synthetic_dataset()
    return {key: dict(body) for key, body in dataset.info_features.items()}


def _full_stats(info_features: dict[str, dict[str, object]]) -> dict[str, dict[str, float]]:
    """Return a `meta/stats.json`-shaped map with every metric present for every feature.

    The metric key set is `METRIC_KEYS` (the ten `compute_stats` metrics, quantiles
    included); values are placeholders because preflight reads only key presence.

    Args:
        info_features: The feature map whose keys to synthesize stats for.

    Returns:
        (dict) Feature key to a full metric map.
    """
    return {key: dict.fromkeys(METRIC_KEYS, 0.0) for key in info_features}


def pi05_policy(**overrides: object) -> PolicyPreflightSpec:
    """Build a pi0.5-like preflight policy spec.

    Args:
        overrides: `rename_map` / `input_features` passed through to the spec.

    Returns:
        (PolicyPreflightSpec) A QUANTILES-normalized spec.
    """
    return PolicyPreflightSpec(
        name="pi05",
        normalization_modes=PI05_NORMALIZATION,
        **overrides,  # type: ignore[arg-type]
    )


def smolvla_policy(**overrides: object) -> PolicyPreflightSpec:
    """Build a smolvla-like preflight policy spec (MEAN_STD, no quantiles).

    Args:
        overrides: `rename_map` / `input_features` passed through to the spec.

    Returns:
        (PolicyPreflightSpec) A MEAN_STD-normalized spec.
    """
    return PolicyPreflightSpec(
        name="smolvla",
        normalization_modes=SMOLVLA_NORMALIZATION,
        **overrides,  # type: ignore[arg-type]
    )


def clean_pair() -> tuple[DatasetPreflightInput, PolicyPreflightSpec]:
    """The valid dataset/policy pair — the `CG-4A-02e` PASS case.

    Returns:
        (tuple) The unmodified fixture input and a pi0.5 policy with full stats.
    """
    info = _clean_info()
    return DatasetPreflightInput(info, _full_stats(info)), pi05_policy()


def fault_torque_stripped() -> FaultCase:
    """`CG-4A-02a` — `.torque` removed from `names`, `observation.state` shape kept 48.

    The config must NOT be misjudged as a 48-wide vel/torque recording: the `names`
    carry no `.torque`, so it is a different configuration, and the retained shape
    now disagrees with the shorter `names`.

    Returns:
        (FaultCase) A case that must BLOCK on an observation-config fault.
    """
    info = _clean_info()
    state = info[OBSERVATION_STATE_KEY]
    state["names"] = [n for n in state["names"] if not n.endswith(TORQUE_SUFFIX)]
    # shape stays [48] — the whole point of the fault
    return FaultCase(
        gate_id="CG-4A-02a",
        dataset=DatasetPreflightInput(info, _full_stats(info)),
        policy=pi05_policy(),
        expected_code=PreflightCode.OBSERVATION_STATE_ORDER,
    )


def fault_rename_rotation() -> FaultCase:
    """`CG-4A-02b` — a `rename_map` that rotates the `names` order by one channel.

    The silent-failure archetype: `build_dataset_frame` indexes by `names` order, so
    a one-channel rotation misaligns every channel with no exception.

    Returns:
        (FaultCase) A case that must BLOCK on an observation-config order fault.
    """
    info = _clean_info()
    canonical = observation_state_names(bimanual=True, use_velocity_and_torque=True)
    rotate_by_one = {
        canonical[index]: canonical[(index + 1) % len(canonical)] for index in range(len(canonical))
    }
    return FaultCase(
        gate_id="CG-4A-02b",
        dataset=DatasetPreflightInput(info, _full_stats(info)),
        policy=pi05_policy(rename_map=rotate_by_one),
        expected_code=PreflightCode.OBSERVATION_STATE_ORDER,
    )


def fault_quantiles_removed() -> FaultCase:
    """`CG-4A-02c` — `q01`/`q99` removed from the stats, paired with pi0.5.

    Returns:
        (FaultCase) A case that must BLOCK on a missing-quantile fault.
    """
    info = _clean_info()
    stats = _full_stats(info)
    for key in (OBSERVATION_STATE_KEY, "action"):
        for metric in ("q01", "q99"):
            stats[key].pop(metric, None)
    return FaultCase(
        gate_id="CG-4A-02c",
        dataset=DatasetPreflightInput(info, stats),
        policy=pi05_policy(),
        expected_code=PreflightCode.QUANTILE_STATS_MISSING,
    )


def fault_timestamp_promoted() -> FaultCase:
    """`CG-4A-02d` — `timestamp` renamed into the `observation` policy namespace.

    Returns:
        (FaultCase) A case that must BLOCK on a structural-exclusion promotion.
    """
    info = _clean_info()
    promote = {TIMESTAMP_META_KEY: f"observation.{TIMESTAMP_META_KEY}"}
    return FaultCase(
        gate_id="CG-4A-02d",
        dataset=DatasetPreflightInput(info, _full_stats(info)),
        policy=pi05_policy(rename_map=promote),
        expected_code=PreflightCode.STRUCTURAL_FEATURE_PROMOTED,
    )


def all_fault_cases() -> tuple[FaultCase, ...]:
    """Return every fault case, one per detection gate.

    Returns:
        (tuple[FaultCase, ...]) The four fault-injection cases.
    """
    return (
        fault_torque_stripped(),
        fault_rename_rotation(),
        fault_quantiles_removed(),
        fault_timestamp_promoted(),
    )
