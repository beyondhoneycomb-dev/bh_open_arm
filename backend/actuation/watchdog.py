"""The action-stream watchdog that feeds the gateway's FRESHNESS stage (`03` FR-MOT-058 ②).

Clamping a torque bounds how hard the arm pushes and says nothing about how long. A producer
that dies mid-stream leaves its last command standing, and on an arm with no mechanical brake a
standing feed-forward torque keeps pushing against whatever it was pushing against.

The gateway already refuses a source older than its freshness window. What it cannot do is
measure that age: it holds no clock and takes `source_age_sec` from its caller. So the measuring
lives here and is shared by every command path, because the failure it prevents is invisible
from inside the gateway — a path that passes a hardcoded zero has a FRESHNESS stage that runs on
every command and can never fire, and the filter cannot tell that apart from a healthy stream.
"""

from __future__ import annotations

from backend.actuation.clock import Clock

# What the opening command of a session reports. Nothing preceded it to be late against, and
# refusing it would leave no first command to start a stream with.
FIRST_COMMAND_GAP_SEC = 0.0


class ActionStreamWatchdog:
    """Measures the silence before each judged command, on one command path's clock.

    Ownership: one watchdog per command path, holding that path's `Clock` and the arrival time
    of the last command it judged. Not thread-safe — it is driven from whichever thread calls
    the gateway.

    The judgement is per gap, not a latch: a lapsed command is refused and the next command is
    measured from it, so a producer that resumes is served again. Holding until an operator
    acknowledges is the collision guard's mechanism, not this one.
    """

    def __init__(self, clock: Clock) -> None:
        """Wire the watchdog to the clock its path measures intervals on.

        Args:
            clock: The monotonic source. A fixture passes a `ManualClock` so an elapsed
                interval is a stated fact rather than a race against the test runner.
        """
        self._clock = clock
        self._last_action_at: float | None = None

    def gap_sec(self) -> float:
        """Return the silence preceding the command arriving now, and count it as judged.

        Reading the gap and marking the command are one operation deliberately. Split in two,
        a path that reads and forgets to mark measures every command against the first one and
        never goes stale — which is the same arm-keeps-pushing outcome as passing a constant
        zero, and just as invisible downstream.

        Returns:
            (float) Seconds since the previous judged command, or `FIRST_COMMAND_GAP_SEC` for
            the first command of a session.
        """
        now = self._clock.now()
        gap = FIRST_COMMAND_GAP_SEC if self._last_action_at is None else now - self._last_action_at
        self._last_action_at = now
        return gap
