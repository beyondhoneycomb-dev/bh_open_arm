"""Stand-ins for the two things a round touches: the motors bus and the host's CAN channels.

No test here opens a socket or binds a port. The bus double answers in the units the real one
answers in — degrees, one entry per name asked for whether the motor replied or not — because a
double that answered in radians would let the conversion these tests exist to pin disappear
without a single failure.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

from backend.can.lock import LockManager
from ops.hw.canbind import CanChannel

# The temperatures a powered DM motor reports. Non-zero on purpose: all five state fields zero
# together is what `is_cache_initialiser` reads as "this motor never answered", so a double that
# left the temperatures at zero would look silent while reporting a position.
AMBIENT_TEMP_C = 24.0

# Two channels of one adapter, the shape this rig actually presents. The keys carry different
# `dev_id` values, which is the only axis that separates two channels of one multi-channel
# adapter — the `ID_PATH` half is identical for both.
ADAPTER_ID_PATH = "pci-0000:80:14.0-usb-0:7.1.2:1.0"
INTERFACE_A = "can0"
INTERFACE_B = "can1"

# The angle every joint sits at before the operator touches anything, degrees.
RESTING_ANGLE_DEG = 12.0


class FakeChannelBus:
    """A motors bus that answers a fixed angle per joint, in the degrees the real bus reports.

    Attributes:
        angles_deg: The angle each motor answers with. Mutable so a test can move an arm between
            the two readings the way the operator does.
        is_connected: Whether the channel is open.
        read_motors: The motor list handed to each read, in call order.
        disconnected_cutting_torque: One entry per disconnect, True when it cut torque.
    """

    def __init__(self, motor_names: tuple[str, ...], angle_deg: float) -> None:
        """Build a bus answering one angle for every named motor.

        Args:
            motor_names: The motors this bus is registered with.
            angle_deg: The angle they all report until a test moves them.
        """
        self.angles_deg = dict.fromkeys(motor_names, angle_deg)
        self.is_connected = True
        self.read_motors: list[list[str]] = []
        self.disconnected_cutting_torque: list[bool] = []

    def sync_read_all_states(self, motors: list[str]) -> dict[str, dict[str, float]]:
        """Return one state per named motor, positions in degrees."""
        self.read_motors.append(list(motors))
        return {
            name: {
                "position": self.angles_deg[name],
                "velocity": 0.0,
                "torque": 0.0,
                "temp_mos": AMBIENT_TEMP_C,
                "temp_rotor": AMBIENT_TEMP_C,
            }
            for name in motors
        }

    def disconnect(self, disable_torque: bool = True) -> None:
        """Close the channel, recording whether the caller asked for a torque cut."""
        self.disconnected_cutting_torque.append(disable_torque)
        self.is_connected = False


class SilentMotorBus(FakeChannelBus):
    """A bus with one motor that has never answered, so its state is the zeroed cache.

    The real bus returns an entry for every name asked for whether a frame came back or not, and
    the entry for a motor that said nothing is the cache it was constructed with: position 0.0,
    which on this arm is a plausible pose.
    """

    def __init__(self, motor_names: tuple[str, ...], angle_deg: float, silent: str) -> None:
        """Build a bus whose one named motor answers nothing.

        Args:
            motor_names: The motors this bus is registered with.
            angle_deg: The angle the answering motors report.
            silent: The motor that answers the zeroed cache instead.
        """
        super().__init__(motor_names, angle_deg)
        self._silent = silent

    def sync_read_all_states(self, motors: list[str]) -> dict[str, dict[str, float]]:
        """Return the answering motors' states and the silent one's zeroed cache."""
        states = super().sync_read_all_states(motors)
        if self._silent in states:
            states[self._silent] = dict.fromkeys(states[self._silent], 0.0)
        return states


class MoveArm:
    """Stands in for the operator: moves one joint of one channel between the two readings.

    `identify_moved_channel` calls this where the real round waits out the move window, so a test
    supplies the motion the same way the bench does — after the baseline, before the second read.
    """

    def __init__(self, bus: FakeChannelBus, motor: str, delta_deg: float) -> None:
        """Move one motor by a fixed amount when called.

        Args:
            bus: The channel's bus.
            motor: The joint the operator's hand reaches.
            delta_deg: How far it moves, degrees.
        """
        self._bus = bus
        self._motor = motor
        self._delta_deg = delta_deg

    def __call__(self) -> None:
        """Apply the move."""
        self._bus.angles_deg[self._motor] += self._delta_deg


class NobodyMoves:
    """Stands in for an operator who touched nothing."""

    def __call__(self) -> None:
        """Do nothing, which is what a round with no motion in it records."""


def channel(interface: str, dev_id: str, state: str = "ERROR-ACTIVE") -> CanChannel:
    """One CAN channel as `list_can_channels` reports it."""
    return CanChannel(
        interface=interface,
        id_path=ADAPTER_ID_PATH,
        dev_id=dev_id,
        driver="peak_usb",
        state=state,
        bitrate_bps=1_000_000,
    )


def two_channels(state: str = "ERROR-ACTIVE") -> tuple[CanChannel, ...]:
    """The pair of channels this rig presents."""
    return (channel(INTERFACE_A, "0x0", state), channel(INTERFACE_B, "0x1", state))


def channel_lister(channels: tuple[CanChannel, ...]) -> Any:
    """Return a stand-in for `list_can_channels` that reports a fixed set."""
    return functools.partial(list, channels)


def lock_manager_factory(lock_dir: Path) -> Any:
    """Return a `LockManager` factory confined to a temporary lock directory."""
    return functools.partial(LockManager, lock_dir=str(lock_dir))
