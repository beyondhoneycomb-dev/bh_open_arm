"""Fault-injection fixtures for the WP-4A-03 degenerate detector (SHAPE-IM(3)).

`02c` §1.3 defines every detection gate as MUST-FIRE-on-fault: a stationary `.vel`
channel forced to a constant 0, a non-contact `.torque` channel forced near-
constant. Each fixture starts from the COMMITTED synthetic 48-dim dataset
(`contracts.fixtures.synthetic_dataset`) and the frozen metric-key set
(`backend.dataset.stats.constants.METRIC_KEYS`) — consumed by reference, never re-
spelt — and builds a `meta/stats.json`-shaped per-channel metric-array map, then
collapses exactly one channel's statistics. The target channel is chosen BY NAME
(`FR-TRN-063` discipline), so a fixture cannot accidentally depend on a channel's
position.

A degenerate fixture is only useful if it makes the detector fire; the clean
baseline is only useful if the detector leaves it alone. That mutual definition is
the SHAPE-IM cross-check (`02c` §0.5).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.dataset.stats.constants import METRIC_KEYS
from backend.training.degenerate.constants import (
    MAX_KEY,
    MIN_KEY,
    Q01_KEY,
    Q99_KEY,
    STD_KEY,
)
from backend.training.preflight import ObservationConfig, derive_observation_config
from contracts.fixtures.synthetic_dataset import build_synthetic_dataset
from contracts.recorder import (
    OBSERVATION_STATE_KEY,
    TORQUE_SUFFIX,
    VELOCITY_SUFFIX,
)

# A per-channel std well clear of any degenerate value: every healthy channel sits
# near O(1), decades above the eps floor, so a derivation harness sees two clusters
# and a threshold placed between them flags only the collapsed channel.
_HEALTHY_STD = 1.0
# A healthy channel's symmetric extent and quantile span, both O(1) — chosen so the
# MIN_MAX and QUANTILES statistics are also decades above degenerate.
_HEALTHY_HALF_RANGE = 2.5
_HEALTHY_HALF_QSPAN = 2.0

# The near-constant residual of a non-contact torque channel: not exactly 0 (a real
# sensor jitters), but decades below a healthy channel — the case the eps floor
# amplifies (`02c` §1.3 physics block).
_NONCONTACT_RESIDUAL = 1e-9


@dataclass(frozen=True)
class DegenerateCase:
    """One degenerate-injection case and where the fault was placed.

    Attributes:
        gate_id: The `02c` §1.3 acceptance check this case exercises.
        config: The observation configuration (derived from the fixture info).
        stats: The `meta/stats.json`-shaped map with one channel collapsed.
        target_channel: The channel name the fault was injected on — what the
            detector must locate.
    """

    gate_id: str
    config: ObservationConfig
    stats: dict[str, dict[str, list[float]]]
    target_channel: str


def _config() -> ObservationConfig:
    """Derive the 48-dim observation configuration from the committed fixture."""
    dataset = build_synthetic_dataset()
    return derive_observation_config(dataset.info_features)


def _healthy_state_stats(names: tuple[str, ...]) -> dict[str, list[float]]:
    """Build a full per-channel metric-array map with every channel healthy.

    Every metric key in `METRIC_KEYS` is present (so no mode reads a missing key),
    and every channel's std / extent / quantile span is O(1).

    Args:
        names: The `observation.state` channel names, fixing the array length.

    Returns:
        (dict[str, list[float]]) Metric key -> per-channel array.
    """
    width = len(names)
    arrays = {metric: [0.0] * width for metric in METRIC_KEYS}
    for index in range(width):
        arrays[STD_KEY][index] = _HEALTHY_STD
        arrays[MIN_KEY][index] = -_HEALTHY_HALF_RANGE
        arrays[MAX_KEY][index] = _HEALTHY_HALF_RANGE
        arrays[Q01_KEY][index] = -_HEALTHY_HALF_QSPAN
        arrays[Q99_KEY][index] = _HEALTHY_HALF_QSPAN
    return arrays


def _channel_by_suffix(names: tuple[str, ...], suffix: str) -> str:
    """Return a channel name carrying a suffix, chosen by name not by position."""
    for name in names:
        if name.endswith(suffix):
            return name
    raise AssertionError(f"fixture has no {suffix} channel; use_velocity_and_torque must be on")


def _collapse_constant_zero(arrays: dict[str, list[float]], index: int) -> None:
    """Collapse a channel to a constant 0: std / extent / quantile span all 0."""
    for metric in (STD_KEY, MIN_KEY, MAX_KEY, Q01_KEY, Q99_KEY):
        arrays[metric][index] = 0.0


def _collapse_near_constant(arrays: dict[str, list[float]], index: int) -> None:
    """Collapse a channel to a near-constant residual, decades below healthy."""
    arrays[STD_KEY][index] = _NONCONTACT_RESIDUAL
    arrays[MIN_KEY][index] = -_NONCONTACT_RESIDUAL
    arrays[MAX_KEY][index] = _NONCONTACT_RESIDUAL
    arrays[Q01_KEY][index] = -_NONCONTACT_RESIDUAL
    arrays[Q99_KEY][index] = _NONCONTACT_RESIDUAL


def clean_stats() -> tuple[ObservationConfig, dict[str, dict[str, list[float]]]]:
    """The all-healthy baseline — the negative control the detector must leave alone.

    Returns:
        (tuple) The config and a stats map with every state channel healthy.
    """
    config = _config()
    return config, {OBSERVATION_STATE_KEY: _healthy_state_stats(config.names)}


def fault_stationary_vel() -> DegenerateCase:
    """`CG-4A-03a` — a `.vel` channel forced to a constant 0 (stationary joint).

    Returns:
        (DegenerateCase) A case whose chosen `.vel` channel is degenerate under
            every mode; the detector must locate it by joint and component.
    """
    config = _config()
    arrays = _healthy_state_stats(config.names)
    target = _channel_by_suffix(config.names, VELOCITY_SUFFIX)
    _collapse_constant_zero(arrays, config.names.index(target))
    return DegenerateCase(
        gate_id="CG-4A-03a",
        config=config,
        stats={OBSERVATION_STATE_KEY: arrays},
        target_channel=target,
    )


def fault_noncontact_torque() -> DegenerateCase:
    """`CG-4A-03b` — a `.torque` channel forced near-constant (non-contact span).

    Returns:
        (DegenerateCase) A case whose chosen `.torque` channel is degenerate; the
            detector must locate it by joint and component.
    """
    config = _config()
    arrays = _healthy_state_stats(config.names)
    target = _channel_by_suffix(config.names, TORQUE_SUFFIX)
    _collapse_near_constant(arrays, config.names.index(target))
    return DegenerateCase(
        gate_id="CG-4A-03b",
        config=config,
        stats={OBSERVATION_STATE_KEY: arrays},
        target_channel=target,
    )


def per_mode_divergent_channel() -> tuple[tuple[str, ...], dict[str, list[float]]]:
    """A single channel whose three mode-statistics differ, for the CG-4A-03c proof.

    `std` is 0 while `max−min` is 5.0 and `q99−q01` is 4.0, so a detector that read
    the wrong metric for a mode would give the wrong verdict. It exists only to prove
    each mode reads its own statistic (`02c` §1.3 ③).

    Returns:
        (tuple) A one-channel `names` tuple and its metric-array map.
    """
    names = ("left_joint_1.vel",)
    arrays = {metric: [0.0] for metric in METRIC_KEYS}
    arrays[STD_KEY] = [0.0]
    arrays[MIN_KEY] = [-2.5]
    arrays[MAX_KEY] = [2.5]
    arrays[Q01_KEY] = [-2.0]
    arrays[Q99_KEY] = [2.0]
    return names, arrays


def all_degenerate_cases() -> tuple[DegenerateCase, ...]:
    """Return every degenerate-injection case, one per detection gate.

    Returns:
        (tuple[DegenerateCase, ...]) The stationary-vel and non-contact-torque cases.
    """
    return (fault_stationary_vel(), fault_noncontact_torque())
