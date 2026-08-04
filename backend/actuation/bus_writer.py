"""The real CAN writers and the drop counter — the actuation/bus boundary (`WP-1-03`).

Everything here sits at the single seam between the actuation spine and a real
`DamiaoMotorsBus`, and is owned by the actuation tree so the single-writer static
scan exempts its (legitimate) use of the CAN write symbol:

- `BusCanWriter` is the one-channel production `CanWriter`. It turns the scheduler's
  `ExecutedMitCommand` batch into the 5-tuple `_mit_control_batch` takes and sends
  it. The whole point is the fifth element: LeRobot's stock `send_action` hardcodes
  `tau` (and `dq`) to `0` (`12` §2.7.0), while the bus-level `_mit_control_batch`
  already accepts a torque argument (`16` §10.1) — so releasing the hardcode is
  nothing but routing the emitted command's `tau` into that slot (acceptance ⑱).
  There is deliberately no `disable_torque` here: the stop path is a hold frame
  (`04` NFR-MAN-002, acceptance ⑬).

- `BimanualCanWriter` is the two-channel production `CanWriter`, and it is what a
  bimanual rig needs instead: one emission is `BIMANUAL_BATCH_WIDTH` slots wide
  across two channels whose eight motor names are the same eight names, so a
  `BusCanWriter` handed all sixteen names over one channel writes the second arm's
  angles onto the first arm's motors. `ArmWriteSlots` is the per-arm half it splits
  on, and it lives here for the same reason the writer does — a reference to the CAN
  write symbol outside `backend/actuation` is what `staticcheck` calls a producer
  reaching for the handle, so the type the writer consumes cannot live in the tree
  that builds it.

- `DropCounter` surfaces the CAN packet-drop count LeRobot only logs. `_batch_refresh`
  reuses the last known state on a drop and emits `logger.warning("Packet drop: …")`
  and nothing else (`01` FR-SYS-018) — the count never becomes an observation
  feature. Forking LeRobot to add a counter is out (`01` FR-SYS-003), so this
  attaches a counting handler to the Damiao logger by name and exposes the tally,
  which is what lets the follower report it under `can_packet_drop_count`
  (acceptance ⑮) — distinct from the upstream warning that vanishes.

`MitBus` is a structural type so this module imports no robot stack: the light lane
never has `lerobot` installed, and the scheduler must stay importable there. A real
`DamiaoMotorsBus` satisfies it; a fixture bus does too.

Slot order inside a half is the frozen layout order and this module does not check it:
the whole actuation tree addresses the layout by index and never by name — `MIT_BATCH_WIDTH`,
`positions_to_batch` and the emission itself all do — and a name-order check here would be
the one place in the tree that imports the layout, for a plan that is built from it in a
single place. The order is therefore the plan builder's guarantee, not the writer's.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from backend.actuation.can_writer import MIT_BATCH_WIDTH
from contracts.action import ExecutedMitCommand
from contracts.units import rad_per_sec_to_deg_per_sec, rad_to_deg

# The width of one full bimanual emission. Named here as well so callers building a writer for
# the whole command can assert it without reaching into the CAN-writer module.
BIMANUAL_BATCH_WIDTH = MIT_BATCH_WIDTH

# The Damiao motors bus logs a packet drop with this message prefix (`damiao.py`
# `_batch_refresh`). Matching on the prefix is what turns the upstream warning into
# a counted observation without touching LeRobot's source.
DROP_LOG_PREFIX = "Packet drop"

# The logger name the Damiao bus writes to (`lerobot.motors.damiao.damiao`). Named
# as a string so this module pulls in no robot stack in the light lane.
DAMIAO_LOGGER_NAME = "lerobot.motors.damiao.damiao"

# The state fields a motor reply fills. All of them zero together is the bus's cache initialiser
# rather than a reading: a powered DM motor reports its MOS and rotor temperatures in degrees
# Celsius, so ambient alone puts those above zero.
ANSWERED_STATE_FIELDS = ("position", "velocity", "torque", "temp_mos", "temp_rotor")


def is_cache_initialiser(state: Mapping[str, float]) -> bool:
    """Report whether a state is the bus's zeroed cache entry rather than a reply.

    `sync_read_all_states` returns an entry for every motor it was asked about whether or not a
    frame came back, so the mapping's keys prove nothing about which motors answered. The drop
    log is the primary signal and this is the backstop: the log is a contract the vendor can
    reword without changing an API, the handler that reads it is attachable and detachable, and
    neither of those failures touches the values. This test does.

    It only catches a motor that has never answered, because the cache holds a real if stale
    reading once one has. That is the case worth catching separately — the initialiser is
    position zero, which on an arm hanging at the URDF zero is the horizontal.

    Args:
        state: One motor's state as the bus returned it.

    Returns:
        (bool) True when every field a reply fills is zero.
    """
    return all(float(state.get(field, 0.0)) == 0.0 for field in ANSWERED_STATE_FIELDS)


class MitBus(Protocol):
    """The one bus capability `BusCanWriter` needs: a batched MIT write.

    A real `DamiaoMotorsBus` and any fixture bus both satisfy this. Keeping it
    structural means the writer depends on the shape, not on importing LeRobot.
    """

    def _mit_control_batch(
        self, commands: dict[str, tuple[float, float, float, float, float]]
    ) -> None:
        """Send one batched MIT frame: motor name to `(kp, kd, pos_deg, vel_deg_s, tau_nm)`."""
        ...


def bus_command_tuple(command: ExecutedMitCommand) -> tuple[float, float, float, float, float]:
    """Turn one emitted command into the 5-tuple `_mit_control_batch` takes.

    The position and velocity cross back from the contract's radian audit units to the degrees
    the LeRobot bus API takes (`_encode_mit_packet` re-radianises internally); the torque is
    passed in newton-metres, and it is the emitted command's `tau`, never a hardcoded zero
    (`12` §2.7.0, acceptance ⑱).

    Shared by every writer in this module rather than repeated in each: two writers that
    compute this tuple separately can disagree on which fields cross a unit boundary, and the
    frame that reaches a motor would then depend on which writer the rig was assembled with.

    Args:
        command: One joint's emitted MIT command.

    Returns:
        (tuple[float, float, float, float, float]) `(kp, kd, pos_deg, vel_deg_s, tau_nm)`.
    """
    return (
        command.kp,
        command.kd,
        rad_to_deg(command.q).value,
        rad_per_sec_to_deg_per_sec(command.dq).value,
        command.tau.value,
    )


class BusCanWriter:
    """The production `CanWriter`: the scheduler's sole path to a real motor bus.

    Ownership: holds the one bus handle for its arm and the fixed motor-name order
    the batch indices map to. The scheduler holds exactly one of these (never a
    producer), so every torque-bearing frame between torque-on and torque-off is one
    of its `mit_control_batch` calls.
    """

    def __init__(self, bus: MitBus, motor_names: tuple[str, ...]) -> None:
        """Bind the writer to a bus and the motor order its batch maps to.

        Args:
            bus: The MIT bus this writer sends on.
            motor_names: The motor names, in batch-index order; the batch width must
                match this length on every send.
        """
        self._bus = bus
        self._motor_names = motor_names
        self._write_count = 0

    @property
    def write_count(self) -> int:
        """Total frames actually sent since construction.

        Returns:
            (int) Cumulative successful `mit_control_batch` calls.
        """
        return self._write_count

    def mit_control_batch(self, batch: tuple[ExecutedMitCommand, ...]) -> None:
        """Send one MIT batch, routing each command's feed-forward torque to the bus.

        Args:
            batch: One `ExecutedMitCommand` per motor, in `motor_names` order.

        Raises:
            ValueError: If the batch width does not match the motor count.
        """
        if len(batch) != len(self._motor_names):
            raise ValueError(
                f"MIT batch width {len(batch)} does not match motor count {len(self._motor_names)}"
            )
        commands: dict[str, tuple[float, float, float, float, float]] = {}
        for name, command in zip(self._motor_names, batch, strict=True):
            commands[name] = bus_command_tuple(command)
        self._bus._mit_control_batch(commands)
        self._write_count += 1


@dataclass(frozen=True)
class ArmWriteSlots:
    """One arm's share of the bimanual emission: where it goes, and what each slot addresses.

    Attributes:
        bus: The arm's MIT bus — the one handle this half of a frame is sent on. Which channel
            that is cannot be derived: both arms answer on send ids `0x01–0x08` (`03` §2.1), so
            nothing on the bus tells left from right and a swapped pair is not a detected error.
        slot_names: One entry per slot of this arm's half, in the frozen layout order. `None`
            marks a slot the fitted tool puts no motor behind; nothing answers there, and the
            unanswered frames walk the controller to ERROR-PASSIVE and degrade the joints that
            are present.
    """

    bus: MitBus
    slot_names: tuple[str | None, ...]


class BimanualCanWriter:
    """The production `CanWriter` for a rig whose one emission spans two channels.

    Ownership: holds one bus handle per arm through the slot plan it was built from, and is
    held only by the scheduler. Nothing here decides anything — the batch it splits is the
    emission the decider produced from a target the eight-stage filter already passed, so this
    is downstream of the gateway and is not a second way onto a channel.

    One call is **one** counted write however many channels it touches. The scheduler reads
    this writer's own `write_count` around the call and refuses a tick that did not resolve to
    exactly one, so a fan-out that counted per channel would fail every tick, and one that
    counted per channel and halved it would report a write for a fan-out that half failed.

    Threading: one instance per session, driven from the thread that ticks the scheduler. The
    two sends are sequential on one thread, which is also why a bus that raises mid-fan-out
    leaves the earlier arms commanded and the later ones holding their previous MIT command
    until the RID-9 no-send ceiling — the exception propagates and the count does not advance,
    so the tick fails rather than recording a write that only half happened.
    """

    def __init__(self, arms: tuple[ArmWriteSlots, ...]) -> None:
        """Bind the writer to the per-arm slot plan, refusing a plan that cannot address the rig.

        Args:
            arms: One `ArmWriteSlots` per arm, in the emission's arm-major order — the first
                entry takes the emission's first slots. The order is the caller's declaration
                of which arm occupies which half and cannot be checked here or on the bus.

        Raises:
            ValueError: If the plan does not describe the emission the scheduler will hand
                over. Every case is a plan that looks well-formed and misaddresses the rig: an
                arm whose half is a different width than the others splits the emission at the
                wrong index even when the total is right; an arm with no fitted slot at all
                would make a counted write that put no frame on that channel; and two slots of
                one arm naming the same motor silently drops one joint's angle, because the
                batch a bus takes is keyed by name.
        """
        if not arms:
            raise ValueError("a bimanual writer with no arms has no channel to write on")
        widths = {len(arm.slot_names) for arm in arms}
        if len(widths) != 1:
            raise ValueError(
                f"the arms' halves are {sorted(widths)} slots wide; an emission is split at a "
                "fixed index per arm, so unequal halves address one arm's joints from the "
                "other arm's slots even when the total width is right"
            )
        width = sum(len(arm.slot_names) for arm in arms)
        if width != BIMANUAL_BATCH_WIDTH:
            raise ValueError(
                f"the slot plan covers {width} slots and one emission is {BIMANUAL_BATCH_WIDTH}; "
                "a plan narrower than the frame leaves joints uncommanded and a wider one is "
                "addressed past its end"
            )
        for index, arm in enumerate(arms):
            fitted = [name for name in arm.slot_names if name is not None]
            if not fitted:
                raise ValueError(
                    f"arm {index} of the slot plan has no fitted motor; a write for it would "
                    "put no frame on its channel while still counting as this tick's one "
                    "write, and an arm nobody refreshes falls at the RID-9 no-send ceiling"
                )
            if len(set(fitted)) != len(fitted):
                raise ValueError(
                    f"arm {index} of the slot plan names a motor twice ({sorted(fitted)}); the "
                    "batch a bus takes is keyed by motor name, so the later slot overwrites "
                    "the earlier one and that joint is commanded with another joint's angle"
                )
        self._arms = arms
        self._width = width
        self._write_count = 0

    @property
    def write_count(self) -> int:
        """Total emissions actually carried to every channel since construction.

        Returns:
            (int) Cumulative successful `mit_control_batch` calls — one per emission, not one
            per channel, which is what the scheduler's per-tick single-write guard reads.
        """
        return self._write_count

    def mit_control_batch(self, batch: tuple[ExecutedMitCommand, ...]) -> None:
        """Split one emission arm-major and send each arm's fitted slots on its own channel.

        A slot the plan marks `None` produces no frame at all. Motor `0x08` answered 0 of 20
        polls on both arms of this rig; sixteen unanswered frames took both channels from
        ERROR-ACTIVE to ERROR-PASSIVE, and a degraded controller then affects the seven joints
        that are present, so an unfitted slot is skipped rather than sent and ignored.

        Args:
            batch: One `ExecutedMitCommand` per slot of the whole emission, arm-major in the
                order the arms were declared in.

        Raises:
            ValueError: If the batch is not as wide as the slot plan. A narrower batch would
                leave the last arm reading past its end; a wider one carries joints no channel
                was declared for.
        """
        if len(batch) != self._width:
            raise ValueError(
                f"MIT batch width {len(batch)} does not match the {self._width}-slot plan"
            )
        index = 0
        for arm in self._arms:
            commands: dict[str, tuple[float, float, float, float, float]] = {}
            for name in arm.slot_names:
                command = batch[index]
                index += 1
                if name is None:
                    continue
                commands[name] = bus_command_tuple(command)
            arm.bus._mit_control_batch(commands)
        self._write_count += 1


class _DropLogHandler(logging.Handler):
    """A logging handler that fires a callback on each packet-drop record.

    Kept a named class rather than a closure so the counting side effect has an
    obvious owner; it only recognises records whose message is the Damiao bus's
    packet-drop warning.
    """

    def __init__(self, on_drop: Callable[[], None]) -> None:
        """Bind the handler to the increment callback.

        Args:
            on_drop: Called once per packet-drop record seen.
        """
        super().__init__(level=logging.WARNING)
        self._on_drop = on_drop

    def emit(self, record: logging.LogRecord) -> None:
        """Increment the tally when the record is a packet-drop warning."""
        if record.getMessage().startswith(DROP_LOG_PREFIX):
            self._on_drop()


class DropCounter:
    """A CAN packet-drop tally, sourced from the Damiao logger the bus writes to.

    Ownership: owns a logging handler it attaches to the Damiao logger. The upstream
    only logs a drop and reuses the last state (`01` FR-SYS-018), so counting those
    records is the one non-forking way to surface the drop count as an observation
    feature. Threading: the handler may fire on the bus-read thread, so the count is
    guarded by a lock and read atomically.
    """

    def __init__(self, logger_name: str = DAMIAO_LOGGER_NAME) -> None:
        """Build the counter without yet attaching it.

        Args:
            logger_name: The logger whose packet-drop warnings to count.
        """
        self._logger_name = logger_name
        self._lock = threading.Lock()
        self._count = 0
        self._handler = _DropLogHandler(self._increment)

    @property
    def count(self) -> int:
        """The number of packet drops counted since `attach`.

        Returns:
            (int) The drop tally, exposed as the `can_packet_drop_count` feature.
        """
        with self._lock:
            return self._count

    def attach(self) -> None:
        """Start counting: add the handler to the Damiao logger."""
        logging.getLogger(self._logger_name).addHandler(self._handler)

    def detach(self) -> None:
        """Stop counting: remove the handler from the Damiao logger."""
        logging.getLogger(self._logger_name).removeHandler(self._handler)

    def _increment(self) -> None:
        """Record one packet drop, guarded so a read never races the increment."""
        with self._lock:
            self._count += 1
