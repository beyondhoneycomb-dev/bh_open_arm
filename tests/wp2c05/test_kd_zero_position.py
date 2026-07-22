"""Acceptance ⑤ — a position command with `kd == 0` is never sent (`FR-SAF-040`).

Damiao's manual warns that position control with zero damping makes the motor vibrate
or run away. So any reaction that drives a stiffness-controlled position is refused when
its damping is zero, and the dangerous crossing — returning to position control from
GRAVITY_COMP's `(kp=0, kd=0)` — is guarded on the resume path. GRAVITY_COMP itself is
exempt: with `kp=0` it commands no position, it is a pure torque feed-forward.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.reaction import (
    KdZeroPositionCommandError,
    ReactionContext,
    ReactionStrategy,
    TorqueChannel,
    build_reaction_command,
    resume_to_position,
)
from contracts.units import Rad


def test_stop_hold_with_zero_damping_is_refused(
    context: ReactionContext, channel_available: TorqueChannel
) -> None:
    """STOP_HOLD commands a position, so zero damping on a joint is refused."""
    zero_kd = dataclasses.replace(context, kd_orig=tuple(0.0 for _ in range(context.width)))
    with pytest.raises(KdZeroPositionCommandError):
        build_reaction_command(ReactionStrategy.STOP_HOLD, zero_kd, channel_available)


def test_retract_with_zero_damping_is_refused(
    context: ReactionContext, channel_available: TorqueChannel
) -> None:
    """RETRACT drives a lowered-stiffness position, so zero damping is refused too."""
    zero_kd = dataclasses.replace(context, kd_orig=tuple(0.0 for _ in range(context.width)))
    with pytest.raises(KdZeroPositionCommandError):
        build_reaction_command(ReactionStrategy.RETRACT, zero_kd, channel_available)


def test_gravity_comp_with_zero_damping_is_allowed(
    context: ReactionContext, channel_available: TorqueChannel
) -> None:
    """GRAVITY_COMP's `(kp=0, kd=0)` is a pure torque command, not a position command."""
    command = build_reaction_command(ReactionStrategy.GRAVITY_COMP, context, channel_available)
    assert command.batch is not None
    assert all(command_i.kp == 0.0 and command_i.kd == 0.0 for command_i in command.batch)


def test_resume_to_position_refuses_zero_damping(context: ReactionContext) -> None:
    """Returning to position control with `kd=0` — the Damiao warning edge — is refused."""
    kp = tuple(40.0 for _ in range(context.width))
    zero_kd = tuple(0.0 for _ in range(context.width))
    with pytest.raises(KdZeroPositionCommandError):
        resume_to_position(kp, zero_kd, context.q_hold)


def test_resume_to_position_admits_nonzero_damping(context: ReactionContext) -> None:
    """A resume with live damping is admitted (the safe crossing back to position)."""
    kp = tuple(40.0 for _ in range(context.width))
    kd = tuple(1.0 for _ in range(context.width))
    batch = resume_to_position(kp, kd, context.q_hold)
    assert len(batch) == context.width
    assert all(command.kd > 0.0 for command in batch)


def test_single_offending_joint_is_reported(
    context: ReactionContext, channel_available: TorqueChannel
) -> None:
    """A single zero-damping joint in an otherwise valid set names its index."""
    kd = list(context.kd_orig)
    kd[3] = 0.0
    one_bad = dataclasses.replace(context, kd_orig=tuple(kd))
    with pytest.raises(KdZeroPositionCommandError) as excinfo:
        resume_to_position(tuple(40.0 for _ in range(context.width)), tuple(kd), context.q_hold)
    assert excinfo.value.joint_index == 3
    # The full reaction build refuses it the same way.
    with pytest.raises(KdZeroPositionCommandError):
        build_reaction_command(ReactionStrategy.STOP_HOLD, one_bad, channel_available)


def test_zero_position_target_is_not_a_zero_damping_violation(
    context: ReactionContext,
) -> None:
    """A zero *position* with live damping is fine — the rule is about kd, not q."""
    kp = tuple(40.0 for _ in range(context.width))
    kd = tuple(1.0 for _ in range(context.width))
    at_zero = tuple(Rad(0.0) for _ in range(context.width))
    batch = resume_to_position(kp, kd, at_zero)
    assert all(command.q.value == 0.0 for command in batch)
