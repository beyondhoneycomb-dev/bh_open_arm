"""Acceptance ④ — POWER_OFF shows a fall warning and requires a double confirmation.

Category 0 (`disable_all()` / CAN `0xFD`) cuts torque with no holding brake, so the arm
falls (`FR-SAF-042`). It is refused unless the operator both acknowledges the fall
warning and separately confirms — two independent flags, so one accidental click cannot
arm a fall. The directive it authorizes names the power-off opcode and carries the
warning text, and it is a directive (not a `disable_torque()` call), keeping the
reaction tree free of the banned stop-path symbol.
"""

from __future__ import annotations

import pytest

from backend.reaction import (
    POWER_OFF_CAN_OPCODE,
    POWER_OFF_FALL_WARNING,
    PowerOffConfirmation,
    PowerOffConfirmationError,
    ReactionCommand,
    ReactionContext,
    ReactionStrategy,
    TorqueChannel,
    build_reaction_command,
)


def _build(
    context: ReactionContext,
    channel: TorqueChannel,
    confirmation: PowerOffConfirmation | None,
) -> ReactionCommand:
    return build_reaction_command(ReactionStrategy.POWER_OFF, context, channel, confirmation)


def test_power_off_refused_without_any_confirmation(
    context: ReactionContext, channel_available: TorqueChannel
) -> None:
    """No confirmation at all refuses the power-off."""
    with pytest.raises(PowerOffConfirmationError):
        _build(context, channel_available, None)


def test_power_off_refused_with_only_warning_acknowledged(
    context: ReactionContext, channel_available: TorqueChannel
) -> None:
    """Acknowledging the warning is not enough — the separate confirmation is required."""
    partial = PowerOffConfirmation(fall_warning_acknowledged=True, confirmed=False)
    with pytest.raises(PowerOffConfirmationError):
        _build(context, channel_available, partial)


def test_power_off_refused_with_only_confirmation(
    context: ReactionContext, channel_available: TorqueChannel
) -> None:
    """Confirming without acknowledging the fall warning is refused."""
    partial = PowerOffConfirmation(fall_warning_acknowledged=False, confirmed=True)
    with pytest.raises(PowerOffConfirmationError):
        _build(context, channel_available, partial)


def test_power_off_authorized_with_double_confirmation(
    context: ReactionContext, channel_available: TorqueChannel
) -> None:
    """Both confirmations present authorize the directive with the opcode and warning."""
    confirmation = PowerOffConfirmation(fall_warning_acknowledged=True, confirmed=True)
    command = _build(context, channel_available, confirmation)
    assert command.directive is not None
    assert command.directive.can_opcode == POWER_OFF_CAN_OPCODE
    assert command.directive.warning == POWER_OFF_FALL_WARNING


def test_fall_warning_mentions_the_fall() -> None:
    """The fall warning text actually warns about the fall (not a generic prompt)."""
    assert "fall" in POWER_OFF_FALL_WARNING.lower()
    assert "brake" in POWER_OFF_FALL_WARNING.lower()
