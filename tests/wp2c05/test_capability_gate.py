"""Acceptance ③ — GRAVITY_COMP / ADMITTANCE / τ_grav STOP_HOLD need `FR-SAF-069`.

The three feed-forward reactions carry a torque (and, for ADMITTANCE, a velocity) the
stock `send_action` hardcodes to zero, so without the `FR-SAF-069` extension they
*cannot exist* (`12` §2.7.0). This is enforced by a raised refusal, not a comment. The
other three reactions do not hard-require the channel: RETRACT degrades to a
position-only retreat, and STOP_DECEL / POWER_OFF are reachable on the stock path.
"""

from __future__ import annotations

import pytest

from backend.reaction import (
    PowerOffConfirmation,
    ReactionContext,
    ReactionStrategy,
    TorqueChannel,
    TorqueChannelUnavailableError,
    build_reaction_command,
    properties,
)

_HARD_REQUIRED = (
    ReactionStrategy.STOP_HOLD,
    ReactionStrategy.GRAVITY_COMP,
    ReactionStrategy.ADMITTANCE,
)


@pytest.mark.parametrize("strategy", _HARD_REQUIRED)
def test_feedforward_reaction_refused_without_channel(
    strategy: ReactionStrategy,
    context: ReactionContext,
    channel_unavailable: TorqueChannel,
) -> None:
    """Each of the three feed-forward reactions raises when the channel is absent."""
    with pytest.raises(TorqueChannelUnavailableError) as excinfo:
        build_reaction_command(strategy, context, channel_unavailable)
    assert excinfo.value.strategy is strategy


@pytest.mark.parametrize("strategy", _HARD_REQUIRED)
def test_feedforward_reaction_builds_with_channel(
    strategy: ReactionStrategy,
    context: ReactionContext,
    channel_available: TorqueChannel,
) -> None:
    """With the channel present each of the three builds and carries `τ_grav`."""
    command = build_reaction_command(strategy, context, channel_available)
    assert command.batch is not None
    assert command.batch[0].tau.value == context.tau_grav[0].value


def test_admittance_also_needs_the_velocity_channel(
    context: ReactionContext,
) -> None:
    """ADMITTANCE needs velocity on top of torque; torque-only still refuses it."""
    torque_only = TorqueChannel(feedforward_torque=True, feedforward_velocity=False)
    with pytest.raises(TorqueChannelUnavailableError) as excinfo:
        build_reaction_command(ReactionStrategy.ADMITTANCE, context, torque_only)
    assert excinfo.value.channel == "velocity"


def test_retract_degrades_without_channel_rather_than_refusing(
    context: ReactionContext,
    channel_unavailable: TorqueChannel,
) -> None:
    """RETRACT is not hard-required: without the channel it retreats but drops `τ_grav`."""
    assert not properties(ReactionStrategy.RETRACT).requires_torque_channel
    command = build_reaction_command(ReactionStrategy.RETRACT, context, channel_unavailable)
    assert command.batch is not None
    assert command.degraded
    assert all(command_i.tau.value == 0.0 for command_i in command.batch)


def test_stop_decel_and_power_off_reachable_on_stock_path(
    context: ReactionContext,
    channel_unavailable: TorqueChannel,
) -> None:
    """STOP_DECEL and POWER_OFF need no feed-forward channel (LeRobot path reachable)."""
    decel = build_reaction_command(ReactionStrategy.STOP_DECEL, context, channel_unavailable)
    assert decel.decel is not None

    confirmation = PowerOffConfirmation(fall_warning_acknowledged=True, confirmed=True)
    power_off = build_reaction_command(
        ReactionStrategy.POWER_OFF, context, channel_unavailable, confirmation
    )
    assert power_off.directive is not None
