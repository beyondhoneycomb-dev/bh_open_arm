"""The `FR-SAF-069` torque/velocity channel capability — the gate three reactions need.

`FR-SAF-069` is the `send_action()` extension that lets a feed-forward torque (and
velocity) reach the bus; the stock LeRobot path hardcodes both to zero
(`openarm_follower.py:340`), so without the extension the three feed-forward
reactions — `STOP_HOLD` with its `τ_grav`, `GRAVITY_COMP`, and `ADMITTANCE` — have no
way to deliver their command and therefore *cannot exist* (`12` §2.7.0). This module
models that capability as a value the reaction builder requires, so "cannot exist
without `FR-SAF-069`" is enforced by a raised error, not left to a comment.

The capability maps to the plugin's `use_velocity_and_torque` switch (`01`
FR-SYS-012): a follower brought up with it false carries no feed-forward channel, and
the gate refuses the three reactions against it exactly as it would against real
hardware missing the extension.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.reaction.strategy import ReactionStrategy, properties


class TorqueChannelUnavailableError(RuntimeError):
    """Raised when a reaction needs a feed-forward channel the follower does not carry.

    Attributes:
        strategy: The reaction that was refused.
        channel: The missing channel — "torque" or "velocity".
    """

    def __init__(self, strategy: ReactionStrategy, channel: str) -> None:
        """Build the refusal, naming the strategy and the channel it lacks.

        Args:
            strategy: The reaction that cannot exist without the channel.
            channel: The missing feed-forward channel.
        """
        super().__init__(
            f"{strategy.value} needs the FR-SAF-069 feed-forward {channel} channel, which this "
            f"follower does not carry (use_velocity_and_torque is off); the stock send_action "
            f"hardcodes {channel} to zero, so this reaction cannot exist (12 §2.7.0)"
        )
        self.strategy = strategy
        self.channel = channel


@dataclass(frozen=True)
class TorqueChannel:
    """Whether `send_action` carries feed-forward torque and velocity (`FR-SAF-069`).

    A position-only follower (the stock LeRobot path) carries neither; the plugin's
    `use_velocity_and_torque` extension carries both. Both are modelled rather than a
    single flag because ADMITTANCE needs velocity on top of torque, and a follower
    could in principle route one without the other.

    Attributes:
        feedforward_torque: Whether a feed-forward `tau` reaches the bus.
        feedforward_velocity: Whether a feed-forward `dq` reaches the bus.
    """

    feedforward_torque: bool
    feedforward_velocity: bool

    @staticmethod
    def available() -> TorqueChannel:
        """The `FR-SAF-069` extension present: both feed-forward channels reach the bus.

        Returns:
            (TorqueChannel) A capability carrying torque and velocity.
        """
        return TorqueChannel(feedforward_torque=True, feedforward_velocity=True)

    @staticmethod
    def unavailable() -> TorqueChannel:
        """The stock path: no feed-forward channel (tau/vel hardcoded to zero).

        Returns:
            (TorqueChannel) A capability carrying neither channel.
        """
        return TorqueChannel(feedforward_torque=False, feedforward_velocity=False)

    @staticmethod
    def from_use_velocity_and_torque(enabled: bool) -> TorqueChannel:
        """Map the plugin's `use_velocity_and_torque` switch to the channel capability.

        Args:
            enabled: The follower's `use_velocity_and_torque` value (`01` FR-SYS-012).

        Returns:
            (TorqueChannel) `available()` when enabled, else `unavailable()`.
        """
        return TorqueChannel.available() if enabled else TorqueChannel.unavailable()


def require_channels(strategy: ReactionStrategy, channel: TorqueChannel) -> None:
    """Refuse a reaction whose required feed-forward channel the follower lacks.

    The three feed-forward reactions (`STOP_HOLD`, `GRAVITY_COMP`, `ADMITTANCE`) cannot
    exist without the torque channel; ADMITTANCE additionally needs the velocity
    channel. The other three impose no feed-forward requirement here — RETRACT merely
    degrades, and STOP_DECEL/POWER_OFF are reachable on the stock path.

    Args:
        strategy: The reaction about to be built.
        channel: The follower's feed-forward channel capability.

    Raises:
        TorqueChannelUnavailableError: If a required channel is absent.
    """
    facts = properties(strategy)
    if facts.requires_torque_channel and not channel.feedforward_torque:
        raise TorqueChannelUnavailableError(strategy, "torque")
    if facts.requires_velocity_channel and not channel.feedforward_velocity:
        raise TorqueChannelUnavailableError(strategy, "velocity")
