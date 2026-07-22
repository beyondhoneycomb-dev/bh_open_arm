"""The six reaction frames match `12` §2.10, and their fixed physical facts hold.

STOP_HOLD holds at the original gains with `τ_grav`; GRAVITY_COMP is pure torque;
RETRACT retreats opposite the residual with a lowered stiffness; ADMITTANCE yields as a
velocity `C·r`; STOP_DECEL is a stop-gated category-1 trajectory; POWER_OFF is a
category-0 directive. The strategy metadata (category, fall, position-control) is the
single source these facts are read from.
"""

from __future__ import annotations

import pytest

from backend.reaction import (
    DEFAULT_STRATEGY,
    POWER_OFF_CAN_OPCODE,
    PowerOffConfirmation,
    PowerOffConfirmationError,
    ReactionContext,
    ReactionStrategy,
    StopCategory,
    TorqueChannel,
    build_reaction_command,
    properties,
)


def test_stop_hold_holds_original_gains_and_gravity(
    context: ReactionContext, channel_available: TorqueChannel
) -> None:
    """STOP_HOLD = MIT(kp_orig, kd_orig, q_hold, 0, τ_grav) per joint."""
    command = build_reaction_command(ReactionStrategy.STOP_HOLD, context, channel_available)
    assert command.batch is not None
    for index, mit in enumerate(command.batch):
        assert mit.kp == context.kp_orig[index]
        assert mit.kd == context.kd_orig[index]
        assert mit.q.value == context.q_hold[index].value
        assert mit.dq.value == 0.0
        assert mit.tau.value == context.tau_grav[index].value
    assert not command.degraded


def test_gravity_comp_is_pure_torque(
    context: ReactionContext, channel_available: TorqueChannel
) -> None:
    """GRAVITY_COMP = MIT(0, 0, 0, 0, τ_grav): compliant, a person can push the arm."""
    command = build_reaction_command(ReactionStrategy.GRAVITY_COMP, context, channel_available)
    assert command.batch is not None
    for index, mit in enumerate(command.batch):
        assert mit.kp == 0.0
        assert mit.kd == 0.0
        assert mit.dq.value == 0.0
        assert mit.tau.value == context.tau_grav[index].value


def test_retract_retreats_opposite_the_residual(
    context: ReactionContext, channel_available: TorqueChannel
) -> None:
    """RETRACT moves the residual joint away from `q_hold` along −r̂ with a low kp."""
    command = build_reaction_command(ReactionStrategy.RETRACT, context, channel_available)
    assert command.batch is not None
    # residual is unit on joint 0, zero elsewhere: joint 0 retreats, the rest hold.
    assert command.batch[0].q.value < context.q_hold[0].value
    assert command.batch[0].kp == context.retract_kp_low
    for index in range(1, context.width):
        assert command.batch[index].q.value == context.q_hold[index].value


def test_admittance_yields_velocity_proportional_to_residual(
    context: ReactionContext, channel_available: TorqueChannel
) -> None:
    """ADMITTANCE = MIT(0, kd, ·, dq=C·r, τ_grav): a yielding velocity command."""
    command = build_reaction_command(ReactionStrategy.ADMITTANCE, context, channel_available)
    assert command.batch is not None
    assert command.batch[0].kp == 0.0
    assert command.batch[0].dq.value == context.admittance_gain * context.residual[0]
    assert command.batch[1].dq.value == 0.0  # zero residual joint yields no velocity


def test_stop_decel_is_stop_gated_category_1(
    context: ReactionContext, channel_available: TorqueChannel
) -> None:
    """STOP_DECEL decelerates, then removes power only after a confirmed stop."""
    command = build_reaction_command(ReactionStrategy.STOP_DECEL, context, channel_available)
    assert command.decel is not None
    assert command.batch is None
    # Power is not removed until the arm is confirmed stopped.
    with pytest.raises(PowerOffConfirmationError):
        command.decel.authorize_power_off(stopped_confirmed=False)
    directive = command.decel.authorize_power_off(stopped_confirmed=True)
    assert directive.can_opcode == POWER_OFF_CAN_OPCODE
    assert properties(ReactionStrategy.STOP_DECEL).category is StopCategory.CAT_1


def test_power_off_is_category_0_directive(
    context: ReactionContext, channel_available: TorqueChannel
) -> None:
    """POWER_OFF is a category-0 directive with the disable-all opcode."""
    confirmation = PowerOffConfirmation(fall_warning_acknowledged=True, confirmed=True)
    command = build_reaction_command(
        ReactionStrategy.POWER_OFF, context, channel_available, confirmation
    )
    assert command.directive is not None
    assert command.batch is None
    assert command.directive.can_opcode == POWER_OFF_CAN_OPCODE
    assert properties(ReactionStrategy.POWER_OFF).category is StopCategory.CAT_0


def test_only_power_off_and_stop_decel_cause_a_fall() -> None:
    """The three compliant/hold reactions keep the arm up; the two power cuts drop it."""
    falls = {strategy for strategy in ReactionStrategy if properties(strategy).causes_fall}
    assert falls == {ReactionStrategy.POWER_OFF, ReactionStrategy.STOP_DECEL}


def test_default_strategy_is_stop_hold() -> None:
    """The default reaction is category-2 STOP_HOLD (`FR-SAF-037`)."""
    assert DEFAULT_STRATEGY is ReactionStrategy.STOP_HOLD
    assert properties(DEFAULT_STRATEGY).category is StopCategory.CAT_2
    assert not properties(DEFAULT_STRATEGY).causes_fall
