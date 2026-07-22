"""Pattern A — the scheduler-internal tap (WP-2B-05, acceptance ①⑥).

The Wave-1 scheduler already emits one `TickRecord` per tick, from *inside* `tick`, to
whatever `TraceSink` it was constructed with (`backend.actuation.scheduler`). This tap
IS that sink: it turns each tick's audit record into a `LogFrame` and hands it to a
`LogSink`. That is the whole of pattern A — logging happens inside the tick, at the tick
rate, by reusing the one scheduler rather than forking it.

Two properties make this a safe tap, and both are structural, not promised:

- It never touches CAN. It receives a `TickRecord` and emits a `LogFrame`; it holds no
  `CanWriter` and opens no socket, so there is no transmit symbol on this path for the
  no-transmit scan to find (acceptance ①).
- It never calls `get_observation`. Pattern A is a tick *condition* — the scheduler uses
  the MIT response as state and does not poll `get_observation` per cycle. This tap adds
  nothing to the tick but a record extraction, so the condition is preserved and the
  static scan finds zero `get_observation` references (acceptance ⑥).

Ownership: the caller constructs the real `ActuationScheduler` with this tap as its
`trace`. The tap does not construct or own the scheduler — wiring a scheduler needs a
`CanWriter`, which must never appear on the logger path.
"""

from __future__ import annotations

from backend.actuation.trace import TickRecord
from backend.friction_log.frame import frame_from_batch
from backend.friction_log.sink import LogSink


class SchedulerLogTap:
    """A `TraceSink` that logs pos/vel/tau from inside each scheduler tick.

    Conforms structurally to `backend.actuation.trace.TraceSink`, so it can be handed to
    `ActuationScheduler` as its trace and be called once per tick, synchronously, within
    `tick`.
    """

    def __init__(self, sink: LogSink) -> None:
        """Wire the tap to a log sink.

        Args:
            sink: Where each tick's frame is emitted.
        """
        self._sink = sink

    def record(self, entry: TickRecord) -> None:
        """Emit one tick's pos/vel/tau frame.

        Called from inside the scheduler tick with the frame that tick wrote. It
        extracts position, velocity and torque and emits them; it performs no bus access
        and no `get_observation` poll.

        Args:
            entry: The tick's audit record, carrying the written MIT batch.
        """
        self._sink.emit(frame_from_batch(entry.index, entry.at, entry.batch))
