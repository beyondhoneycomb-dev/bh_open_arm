"""Name-derived channel selection for the torque/velocity ablation (`02c` §1.6).

`10` FR-TRN-074 [정본] splits the observation and action schemas: with
`use_velocity_and_torque=True` the `observation.state` vector is 24/48-dim, but the
policy output and dataset `action` target stay position-only (8/16). The
"torque·velocity 미포함 정책" of FR-TRN-073 is therefore NOT a re-collection — it is
made by SELECTING the `.pos`-suffix channels out of the existing `names`.

The one rule this module exists to hold (the FR-TRN-063 trap): every index is
DERIVED from the `names` strings by suffix, never taken by position. The width and
per-motor layout of `observation.state` move the moment `use_velocity_and_torque`
toggles, and a `rename_map` may rotate the order, so a positional slice selects a
different physical channel set under a different order while looking correct. A
name-derived selection points at the same channels regardless of order — which is
exactly what `CG-4A-06a` proves.

The suffixes and the `.pos`-by-suffix lookup are imported from `CTR-REC@v1`
(`contracts.recorder`), never re-spelt, so this module cannot drift from the
recorder's channel grammar.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from contracts.recorder import (
    POSITION_SUFFIX,
    TORQUE_SUFFIX,
    VELOCITY_SUFFIX,
    channels_with_suffix,
)

# The per-motor suffixes the action target may never carry. `action` is the
# position command that passed the safety gate and was sent to CAN; `send_action`
# hardcodes vel/torque to 0, so a `.vel`/`.torque` action dimension is a head with
# no feedback (`10` FR-TRN-066/074, `11` FR-INF-074, the triple-canonical rule).
ACTION_TARGET_FORBIDDEN_SUFFIXES = (VELOCITY_SUFFIX, TORQUE_SUFFIX)


class ProjectionKind(StrEnum):
    """Which observation subvector an experiment arm trains on (`10` FR-TRN-073).

    FULL keeps every recorded `observation.state` channel (pos + vel + torque);
    POS_ONLY keeps only the `.pos` channels. The action target is position-only in
    both — the projection changes observation width alone, never the action.
    """

    FULL = "FULL"
    POS_ONLY = "POS_ONLY"


class ActionTargetLeakError(ValueError):
    """A `.vel`/`.torque` channel reached the action target.

    The action target is the training label a policy head learns to emit, and it is
    position-only by contract (`10` FR-TRN-066/074, `11` FR-INF-074). A velocity or
    torque channel here trains a head on a dimension `send_action` never executes
    (tau/vel are hardcoded to 0), so this is refused rather than silently trained.
    """


def select_pos_indices(names: Sequence[str]) -> list[int]:
    """Return the indices of the `.pos` channels, derived from the `names` strings.

    Works for both an `observation.state` name list and an `action` name list — the
    ablation's position-only subvector is the `.pos` channels of whichever vector is
    passed. Indices are found by suffix match (`CTR-REC@v1` `channels_with_suffix`),
    never by position, so a rotated `names` order yields the same physical channel
    set at whatever indices those channels now sit (`10` FR-TRN-063).

    Args:
        names: The channel names of the vector to project.

    Returns:
        (list[int]) The positions of the `.pos` channels, in `names` order.
    """
    return list(channels_with_suffix(names, POSITION_SUFFIX))


def observation_projection_indices(names: Sequence[str], kind: ProjectionKind) -> list[int]:
    """Return the observation indices an arm's projection keeps.

    POS_ONLY selects the `.pos` subvector by name; FULL keeps every channel in its
    recorded order (an order-preserving identity, not a positional assumption about
    which channel sits where).

    Args:
        names: The `observation.state` channel names.
        kind: The projection this arm trains on.

    Returns:
        (list[int]) The kept observation indices, in `names` order.
    """
    if kind is ProjectionKind.POS_ONLY:
        return select_pos_indices(names)
    return list(range(len(names)))


def select_action_target_indices(action_names: Sequence[str]) -> list[int]:
    """Return the action-target indices, refusing any `.vel`/`.torque` channel.

    This is the single chokepoint through which an action-target channel selection
    is produced, so "no `.vel`/`.torque` reaches the action target" holds by
    construction: a forbidden-suffix channel raises before any index is returned,
    and the returned set is exactly the `.pos` channels. A canonical `CTR-REC@v1`
    `action` name list is already position-only, so this is an identity on valid
    input and a refusal on a poisoned one (`CG-4A-06c`).

    Args:
        action_names: The `action` feature channel names.

    Returns:
        (list[int]) The `.pos` indices of the action vector.

    Raises:
        ActionTargetLeakError: When any channel carries a `.vel`/`.torque` suffix.
    """
    leaked = [name for name in action_names if name.endswith(ACTION_TARGET_FORBIDDEN_SUFFIXES)]
    if leaked:
        raise ActionTargetLeakError(
            f"action target carries non-position channels {leaked}; action is position-only and "
            "send_action hardcodes vel/torque=0, so a .vel/.torque target is an unexecuted head "
            "(10 FR-TRN-066/074, 11 FR-INF-074)"
        )
    return select_pos_indices(action_names)
