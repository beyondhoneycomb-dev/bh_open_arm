"""The real CAN writer and the drop counter — the actuation/bus boundary (`WP-1-03`).

Two things live here, both at the single seam between the actuation spine and a
real `DamiaoMotorsBus`, and both owned by the actuation tree so the single-writer
static scan exempts their (legitimate) use of the CAN write symbol:

- `BusCanWriter` is the production `CanWriter`. It turns the scheduler's
  `ExecutedMitCommand` batch into the 5-tuple `_mit_control_batch` takes and sends
  it. The whole point is the fifth element: LeRobot's stock `send_action` hardcodes
  `tau` (and `dq`) to `0` (`12` §2.7.0), while the bus-level `_mit_control_batch`
  already accepts a torque argument (`16` §10.1) — so releasing the hardcode is
  nothing but routing the emitted command's `tau` into that slot (acceptance ⑱).
  There is deliberately no `disable_torque` here: the stop path is a hold frame
  (`04` NFR-MAN-002, acceptance ⑬).

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
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Protocol

from backend.actuation.can_writer import MIT_BATCH_WIDTH
from contracts.action import ExecutedMitCommand
from contracts.units import rad_per_sec_to_deg_per_sec, rad_to_deg

# The Damiao motors bus logs a packet drop with this message prefix (`damiao.py`
# `_batch_refresh`). Matching on the prefix is what turns the upstream warning into
# a counted observation without touching LeRobot's source.
DROP_LOG_PREFIX = "Packet drop"

# The logger name the Damiao bus writes to (`lerobot.motors.damiao.damiao`). Named
# as a string so this module pulls in no robot stack in the light lane.
DAMIAO_LOGGER_NAME = "lerobot.motors.damiao.damiao"


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

        The position and velocity cross back from the contract's radian audit units
        to the degrees the LeRobot bus API takes (`_encode_mit_packet` re-radianises
        internally); the torque is passed in newton-metres, and it is the emitted
        command's `tau`, never a hardcoded zero (`12` §2.7.0, acceptance ⑱).

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
            commands[name] = (
                command.kp,
                command.kd,
                rad_to_deg(command.q).value,
                rad_per_sec_to_deg_per_sec(command.dq).value,
                command.tau.value,
            )
        self._bus._mit_control_batch(commands)
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


# Re-exported so callers building a writer for the full bimanual command can assert
# the scheduler's batch width without reaching into the CAN-writer module.
BIMANUAL_BATCH_WIDTH = MIT_BATCH_WIDTH
