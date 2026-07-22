"""The six collision-reaction strategies and their fixed physical properties.

`FR-SAF-037` fixes exactly six reaction modes and makes `STOP_HOLD` the default
(stop category 2, power kept, no fall). This module owns that enum and the frozen
per-strategy facts the rest of the layer reads instead of re-deriving:

- **which strategies cannot exist without `FR-SAF-069`** — the three that carry a
  feed-forward torque (and, for ADMITTANCE, a velocity) the stock `send_action`
  hardcodes to zero: `STOP_HOLD` (its `τ_grav`), `GRAVITY_COMP`, and `ADMITTANCE`
  (`12` §2.7.0). RETRACT uses `τ_grav` when the channel is present but degrades to a
  position-only retreat without it, so it is *not* in the hard-required set.
- **which strategies drop the arm** — `POWER_OFF` (category 0) always, `STOP_DECEL`
  (category 1) after its decel completes. The three compliant/hold strategies never
  drop it.
- **which strategies command a position** — the ones with a live stiffness term, so
  the `FR-SAF-040` kd≠0 rule applies to them and not to the pure-torque ones.

The metadata is a single frozen table so a seventh strategy, or a change to one
strategy's category, is one edit in one place rather than a scattered set of `if`
chains that can disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.reaction.constants import DEFAULT_STRATEGY_NAME


class StopCategory(Enum):
    """IEC 60204-1 stop category a reaction realises (`FR-SAF-037`, `FR-SAF-053`).

    CAT_0 removes power immediately (POWER_OFF — the arm falls). CAT_1 brings the arm
    to a controlled stop and then removes power (STOP_DECEL). CAT_2 holds with power
    kept on (STOP_HOLD). The compliant strategies (GRAVITY_COMP, RETRACT, ADMITTANCE)
    keep power on and are grouped with the held category — they never remove power.
    """

    CAT_0 = "cat_0"
    CAT_1 = "cat_1"
    CAT_2 = "cat_2"


class ReactionStrategy(Enum):
    """The six — and only six — collision reactions (`FR-SAF-037`)."""

    STOP_HOLD = "STOP_HOLD"
    STOP_DECEL = "STOP_DECEL"
    GRAVITY_COMP = "GRAVITY_COMP"
    RETRACT = "RETRACT"
    ADMITTANCE = "ADMITTANCE"
    POWER_OFF = "POWER_OFF"


# The default reaction resolved from the config-token name (`FR-SAF-037`): a config
# that names no `reaction.mode` gets category-2 STOP_HOLD, not a fall-prone default.
DEFAULT_STRATEGY = ReactionStrategy(DEFAULT_STRATEGY_NAME)


@dataclass(frozen=True)
class StrategyProperties:
    """The fixed physical facts of one reaction strategy.

    Attributes:
        category: The IEC 60204-1 stop category the strategy realises.
        requires_torque_channel: Whether the strategy *cannot exist* without the
            `FR-SAF-069` feed-forward-torque channel — true for the three the spec
            names (STOP_HOLD's τ_grav, GRAVITY_COMP, ADMITTANCE). RETRACT is false:
            it degrades to a position-only retreat rather than becoming unreachable.
        requires_velocity_channel: Whether the strategy needs the `FR-SAF-069`
            feed-forward-velocity channel — true only for ADMITTANCE (`dq_cmd = C·r`).
        causes_fall: Whether the strategy drops the arm (no holding brake) — POWER_OFF
            always, STOP_DECEL after its decel, the rest never.
        commands_position: Whether the strategy drives a stiffness-controlled position,
            so the `FR-SAF-040` kd≠0 rule applies. False for the pure-torque
            (GRAVITY_COMP, ADMITTANCE) and power-removal (POWER_OFF) strategies.
    """

    category: StopCategory
    requires_torque_channel: bool
    requires_velocity_channel: bool
    causes_fall: bool
    commands_position: bool


_PROPERTIES: dict[ReactionStrategy, StrategyProperties] = {
    ReactionStrategy.STOP_HOLD: StrategyProperties(
        category=StopCategory.CAT_2,
        requires_torque_channel=True,
        requires_velocity_channel=False,
        causes_fall=False,
        commands_position=True,
    ),
    ReactionStrategy.STOP_DECEL: StrategyProperties(
        category=StopCategory.CAT_1,
        requires_torque_channel=False,
        requires_velocity_channel=False,
        causes_fall=True,
        commands_position=True,
    ),
    ReactionStrategy.GRAVITY_COMP: StrategyProperties(
        category=StopCategory.CAT_2,
        requires_torque_channel=True,
        requires_velocity_channel=False,
        causes_fall=False,
        commands_position=False,
    ),
    ReactionStrategy.RETRACT: StrategyProperties(
        category=StopCategory.CAT_2,
        requires_torque_channel=False,
        requires_velocity_channel=False,
        causes_fall=False,
        commands_position=True,
    ),
    ReactionStrategy.ADMITTANCE: StrategyProperties(
        category=StopCategory.CAT_2,
        requires_torque_channel=True,
        requires_velocity_channel=True,
        causes_fall=False,
        commands_position=False,
    ),
    ReactionStrategy.POWER_OFF: StrategyProperties(
        category=StopCategory.CAT_0,
        requires_torque_channel=False,
        requires_velocity_channel=False,
        causes_fall=True,
        commands_position=False,
    ),
}


def properties(strategy: ReactionStrategy) -> StrategyProperties:
    """Return the fixed physical facts of a strategy.

    Args:
        strategy: The reaction strategy to look up.

    Returns:
        (StrategyProperties) The strategy's frozen properties.
    """
    return _PROPERTIES[strategy]
