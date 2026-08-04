"""Doubles for standing the production rig assembly up with no CAN adapter present.

Everything the assembly reaches for outside its own code is replaced here and nothing else is:
the motors bus, the channel lock manager, and the persisted channel binding. The assembly
itself runs unmodified, which is the point — what is under test is the wiring, and a test that
reimplemented the wiring would agree with itself.

The single writer is deliberately **not** among them. `BimanualCanWriter` is what the benches
build, so what the bus doubles receive is the production split of a real emission. A double for
the writer would be a second implementation of the one thing whose output is the frame that
reaches a motor, and every assertion about which channel got which half would then be an
assertion about the double.

The bus double records the argument of every call. That argument is the whole acceptance: a bus
call that names no motors walks every motor the bus was constructed with, which on a spatula
build is the id nothing answers on, and from outside the two are indistinguishable unless what
was asked for is kept.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.calibration.schema import MOTOR_ORDER
from backend.endeffector import SIDE_LEFT, SIDE_RIGHT, SIDES
from ops.hw.canbind import ArmRole, ChannelBinding, binding_path, save_binding
from ops.hw.canbind.discovery import CanChannel
from scripts.rig_session import (
    ANSWERED_STATE_FIELDS,
    DAMIAO_BUS_LOGGER,
    PACKET_DROP_PREFIX,
)

# Present angles per arm, and the step between adjacent joints. Distinct across arms so a
# swapped half shows in the emitted frame, and distinct across joints so a mis-slotted joint
# does. Small enough to sit inside every URDF joint limit, so the LIMIT stage clamps nothing.
LEFT_BASE_DEG = 1.0
RIGHT_BASE_DEG = 5.0
JOINT_STEP_DEG = 0.25

# A powered motor's reported MOS and rotor temperature. Any positive value does: what the
# read filter keys on is that a reply is not all-zero, and the zeroed cache is what a silent
# motor yields.
AMBIENT_TEMP_C = 31.0

# Send id per motor name, for the drop record the real bus writes.
SEND_ID_BY_MOTOR = {name: index + 1 for index, name in enumerate(MOTOR_ORDER)}

# What the bus reports for the gripper slot on a spatula build: nothing answers on 0x08, so a
# read of it returns the bus's own cache rather than an answer from a motor.
UNFITTED_SLOT_DEG = 0.0

# The udev position and per-channel index a stored binding is keyed on. One adapter, two
# channels, which is the physical shape on this bench.
STUB_ID_PATH = "pci-0000:00:14.0-usb-0:8:1.0"
STUB_DEV_IDS = ("0x0", "0x1")
STUB_BITRATE_BPS = 1_000_000
STUB_DRIVER = "peak_usb"
STUB_LINK_STATE = "ERROR-ACTIVE"

# The raw angle a persisted zero records against a URDF-zero reference of the same value, so the
# residual is zero and the calibration reads as inside tolerance. The measured rig figure is
# 0.0109° — half a quantisation step — and nothing here depends on which of the two it is.
ZEROED_ANGLE_DEG = 0.0

# Interface names the stub binding resolves the two follower roles to. Deliberately not
# `can0`/`can1`: those are what `PORT_BY_SIDE` guesses, so an arm that opened on them would pass
# a test that used them whether or not it ever read the binding.
STUB_INTERFACES = {SIDE_LEFT: "can7", SIDE_RIGHT: "can9"}


class FakeDamiaoBus:
    """A motors bus that answers reads and records what every call addressed.

    Attributes:
        port: The interface this bus was constructed for — the assertion that the arm opened on
            the channel the binding resolved rather than on the side placeholder.
        motors: The registered motor names, the frozen eight-slot layout.
        read_motors: The motor list handed to each state read, in call order; None for a call
            that named none.
        enabled_motors: The motor list handed to each `enable_torque`, in call order.
        disabled_motors: The motor list handed to each `disable_torque`, in call order.
        sent: One entry per MIT write, each the command dict the write carried.
        disconnected_cutting_torque: One entry per disconnect, True when it cut torque.
    """

    def __init__(self, port: str, base_deg: float, unanswered: tuple[str, ...] = ()) -> None:
        """Build a bus reporting a distinct angle per joint.

        Args:
            port: The CAN interface name this bus was constructed for.
            base_deg: The first joint's angle; each later joint steps up from it.
            unanswered: Fitted motors this bus answers no state for.
        """
        self.port = port
        self.motors = dict.fromkeys(MOTOR_ORDER, 0)
        self.is_connected = False
        self.read_motors: list[list[str] | None] = []
        self.enabled_motors: list[list[str]] = []
        self.disabled_motors: list[list[str]] = []
        self.sent: list[dict[str, tuple[float, float, float, float, float]]] = []
        self.disconnected_cutting_torque: list[bool] = []
        self._unanswered = unanswered
        # Which half of the bus's silent-motor behaviour to reproduce. The two signals the
        # read filter keys on are independent, so a test that needs one alone turns the other
        # off: `stale_cache` gives a silent motor its last real angle instead of a zero, and
        # `report_drops` off is a library that stopped writing the record.
        self.stale_cache = False
        self.report_drops = True
        self._angles = {
            motor: base_deg + JOINT_STEP_DEG * index for index, motor in enumerate(MOTOR_ORDER[:-1])
        }
        self._angles[MOTOR_ORDER[-1]] = UNFITTED_SLOT_DEG

    def connect(self, handshake: bool = True) -> None:  # noqa: ARG002 — bus signature
        """Open the channel, which on the real bus also enables every registered motor.

        Not recorded in `enabled_motors`: that list means "what asked for torque", and the
        assembly assertions that read it as empty are about this code, not about the arm.
        The arm is live once a channel is open — `_assemble_rig` carries that contract.
        """
        self.is_connected = True

    def disconnect(self, disable_torque: bool = True) -> None:
        """Close the channel, recording whether the caller asked for a torque cut."""
        self.disconnected_cutting_torque.append(disable_torque)
        if disable_torque:
            self.disabled_motors.append(list(self.motors))
        self.is_connected = False

    def sync_read_all_states(self, motors: list[str] | None = None) -> dict[str, dict[str, float]]:
        """Return one state per named motor, answering the way the real bus answers.

        `DamiaoMotorsBus` returns an entry for every name asked for whether that motor replied or
        not: a drop reaches the caller as a `logging.WARNING` and the entry carries the zeroed
        cache it was constructed with. A double that omitted the silent motor instead would make
        the fitted-motor refusal fire here and never on the bench, which is the one shape
        divergence that matters — 0.0 deg is the hanging pose and looks plausible.
        """
        self.read_motors.append(None if motors is None else list(motors))
        named = list(self.motors) if motors is None else motors
        states: dict[str, dict[str, float]] = {}
        for motor in named:
            if motor in self._unanswered:
                if self.report_drops:
                    logging.getLogger(DAMIAO_BUS_LOGGER).warning(
                        "%s %s (ID: 0x%02X). Using last known state.",
                        PACKET_DROP_PREFIX,
                        motor,
                        SEND_ID_BY_MOTOR[motor],
                    )
                if self.stale_cache:
                    states[motor] = {
                        "position": self._angles[motor],
                        "velocity": 0.0,
                        "torque": 0.0,
                        "temp_mos": AMBIENT_TEMP_C,
                        "temp_rotor": AMBIENT_TEMP_C,
                    }
                else:
                    states[motor] = dict.fromkeys(ANSWERED_STATE_FIELDS, 0.0)
                continue
            states[motor] = {
                "position": self._angles[motor],
                "velocity": 0.0,
                "torque": 0.0,
                "temp_mos": AMBIENT_TEMP_C,
                "temp_rotor": AMBIENT_TEMP_C,
            }
        return states

    def enable_torque(self, motors: list[str] | None = None) -> None:
        """Record a 0xFC and the motors it addressed."""
        self.enabled_motors.append(list(self.motors) if motors is None else list(motors))

    def disable_torque(self, motors: list[str] | None = None) -> None:
        """Record a 0xFD and the motors it addressed."""
        self.disabled_motors.append(list(self.motors) if motors is None else list(motors))

    def _mit_control_batch(
        self, commands: dict[str, tuple[float, float, float, float, float]]
    ) -> None:
        """Record one MIT write; no socket, no motor."""
        self.sent.append(dict(commands))


@dataclass
class FakeLockManager:
    """A channel lock manager that grants everything and remembers what it held.

    The assembly's contract with it is an order — every channel locked before any socket opens —
    and an order is only observable if the grants and the opens land in one sequence, which is
    what `acquired` and the buses' own connect flag together give.

    Attributes:
        acquired: The interface lists handed to each `acquire_all`, in call order.
        releases: How many times every lock was given back.
        held: The interfaces currently held.
    """

    acquired: list[list[str]] = field(default_factory=list)
    releases: int = 0
    held: set[str] = field(default_factory=set)

    def acquire_all(self, ifaces: list[str]) -> Any:
        """Grant every named lock and record the request."""
        self.acquired.append(list(ifaces))
        self.held.update(ifaces)
        return _Acquired(ok=True, blocked_iface=None, holder=None)

    def release_all(self) -> None:
        """Give every lock back."""
        self.releases += 1
        self.held.clear()

    def is_held(self, iface: str) -> bool:
        """Whether this manager holds one interface — what the connect guard checks per channel."""
        return iface in self.held

    def all_held(self, ifaces: list[str]) -> bool:
        """Whether every named interface is held."""
        return all(iface in self.held for iface in ifaces)

    def held_ifaces(self) -> tuple[str, ...]:
        """The interfaces held, in sorted order."""
        return tuple(sorted(self.held))

    def lock_state(self, ifaces: list[str]) -> tuple[Any, ...]:
        """One state per interface, reported from this manager's own record."""
        return tuple(_LockState(iface=iface, held=iface in self.held) for iface in ifaces)


@dataclass(frozen=True)
class _Acquired:
    """The shape `LockManager.acquire_all` returns, narrowed to what the assembly reads."""

    ok: bool
    blocked_iface: str | None
    holder: str | None


@dataclass(frozen=True)
class _LockState:
    """The shape `LockManager.lock_state` returns, narrowed to what a preflight reads."""

    iface: str
    held: bool


class RefusingLockManager(FakeLockManager):
    """A manager that refuses the second channel, the way another process holding it does."""

    def acquire_all(self, ifaces: list[str]) -> Any:
        """Refuse, naming the channel and its holder."""
        self.acquired.append(list(ifaces))
        return _Acquired(ok=False, blocked_iface=ifaces[-1], holder="another-writer")


def write_stub_binding(config_directory: Path) -> dict[str, str]:
    """Persist a channel binding for both follower roles and return the interfaces it resolves.

    Args:
        config_directory: Where the binding record is written.

    Returns:
        (dict[str, str]) One interface per arm side, as the record resolves them.
    """
    channels = stub_channels()
    save_binding(
        binding_path(config_directory),
        ChannelBinding(
            roles={
                ArmRole.FOLLOWER_LEFT: channels[0].channel_key,
                ArmRole.FOLLOWER_RIGHT: channels[1].channel_key,
            }
        ),
    )
    return dict(STUB_INTERFACES)


def stub_channels() -> tuple[CanChannel, ...]:
    """The two channels this bench presents, keyed the way a stored binding matches them."""
    return tuple(
        CanChannel(
            interface=STUB_INTERFACES[side],
            id_path=STUB_ID_PATH,
            dev_id=dev_id,
            driver=STUB_DRIVER,
            state=STUB_LINK_STATE,
            bitrate_bps=STUB_BITRATE_BPS,
        )
        for side, dev_id in zip(SIDES, STUB_DEV_IDS, strict=True)
    )


def present_deg(base_deg: float, joints: int) -> tuple[float, ...]:
    """The angles an arm whose first joint sits at `base_deg` reports, one per fitted joint."""
    return tuple(base_deg + JOINT_STEP_DEG * index for index in range(joints))


def write_zeroed_calibration(directory: Path, robot_id: str, side: str) -> Path:
    """Persist a calibration whose zero is inside tolerance and survived a power cycle.

    Args:
        directory: The calibration directory.
        robot_id: The instance id the arm loads under.
        side: Which arm.

    Returns:
        (Path) The written calibration file.
    """
    from backend.calibration.atomic_io import calibration_path_for, save_calibration_atomic
    from backend.calibration.schema import MOTOR_COUNT, OpenArmCalibration

    path = calibration_path_for(directory, robot_id)
    save_calibration_atomic(
        path,
        OpenArmCalibration(
            robot_type="oa_openarm_follower",
            robot_id=robot_id,
            side=side,
            motor_zero_raw=[ZEROED_ANGLE_DEG] * MOTOR_COUNT,
            urdf_zero_offset=[ZEROED_ANGLE_DEG] * MOTOR_COUNT,
            gripper_open_rad=0.0,
            gripper_close_rad=0.0,
            joint_signs=[1] * MOTOR_COUNT,
            joint_scale=[1.0] * MOTOR_COUNT,
            zero_power_cycle_verified=True,
            zero_residual_deg=[ZEROED_ANGLE_DEG] * MOTOR_COUNT,
            last_zero_at="2026-07-29T00:00:00+00:00",
        ),
    )
    return path
