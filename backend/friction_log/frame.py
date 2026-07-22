"""The per-tick log frame — the pos/vel/tau audit record the tap emits.

A `LogFrame` is one tick's observable state: its index, the send timestamp, and the
commanded position, velocity and feed-forward torque per joint. It is derived from the
scheduler's own `ExecutedMitCommand` batch (pattern A), so the log records exactly what
was commanded rather than a re-read of the bus.

The physical fields keep their CTR-UNIT tags (q=`Rad`, dq=`RadPerSec`, tau=`Nm`, 12 §2.7):
a log is an AUDIT record, and dropping the units here would be the first place a
57.3x-wrong number could enter unnoticed.
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts.action import ExecutedMitCommand
from contracts.units import Nm, Rad, RadPerSec


@dataclass(frozen=True)
class LogFrame:
    """One tick's logged pos/vel/tau, arm-major across both arms.

    Attributes:
        index: Monotonic tick index the frame was captured at.
        at: Clock reading when the tick wrote its frame, in seconds.
        positions: Commanded joint positions, radians, one per joint.
        velocities: Commanded joint velocities, radians per second.
        torques: Commanded feed-forward torques, newton-metres — AUDIT only.
    """

    index: int
    at: float
    positions: tuple[Rad, ...]
    velocities: tuple[RadPerSec, ...]
    torques: tuple[Nm, ...]


def frame_from_batch(index: int, at: float, batch: tuple[ExecutedMitCommand, ...]) -> LogFrame:
    """Extract a `LogFrame` from a scheduler MIT batch (pattern A).

    The batch is the exact frame the scheduler wrote this tick, already in hand from
    the tick's audit record, so no CAN access happens here.

    Args:
        index: The tick index.
        at: The tick's send timestamp, seconds.
        batch: One `ExecutedMitCommand` per joint.

    Returns:
        (LogFrame) The pos/vel/tau record for this tick.
    """
    return LogFrame(
        index=index,
        at=at,
        positions=tuple(command.q for command in batch),
        velocities=tuple(command.dq for command in batch),
        torques=tuple(command.tau for command in batch),
    )
