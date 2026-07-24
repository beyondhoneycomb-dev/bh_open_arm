"""Live action-queue metering — exhaustion count/ratio and residual series (`FR-INF-012`/`020`).

The metering must be provably *alive*, not decorative: CG-4A-07f pulls an injected
delay on the dummy robot and requires the exhaustion counter to rise in proportion.
So this counter is read every consume tick, whether or not the queue was empty, and
the ratio is exhaustion over total — a metering that never incremented on a starved
tick would fail that gate.

`FR-INF-020` (the live queue-remaining graph) is fed by `residual_series`: each tick
records the queue size *before* the consume, so the series is the exact backlog a UI
would plot. It is bounded to a rolling window so a long rollout does not grow it
without limit.

Threading: a `QueueMeter` is written from the one consume path and read for display.
The offline harness drives it single-threaded under a controlled clock, so no lock is
taken here; a real multi-thread consumer would own its own synchronization around the
tick call, as the mailbox does for its slot.
"""

from __future__ import annotations

from collections import deque

# Rolling window for the residual series feeding the live graph (`FR-INF-020`). A
# graph shows recent backlog, not the whole run; capping the deque keeps memory flat
# across an arbitrarily long rollout without changing the exhaustion counters, which
# are unbounded running totals.
RESIDUAL_SERIES_MAXLEN = 4096


class QueueMeter:
    """Running exhaustion tally and residual backlog series for one action queue.

    Ownership: created and updated by the inference engine's consume path; read by a
    UI or a gate. `tick` is the single mutation point.
    """

    def __init__(self, series_maxlen: int = RESIDUAL_SERIES_MAXLEN) -> None:
        """Start an empty meter.

        Args:
            series_maxlen: Rolling window length for the residual series.
        """
        self._total_ticks = 0
        self._exhaustion_ticks = 0
        self._residual_series: deque[int] = deque(maxlen=series_maxlen)

    @property
    def total_ticks(self) -> int:
        """Number of consume ticks metered since construction or the last reset.

        Returns:
            (int) Total ticks.
        """
        return self._total_ticks

    @property
    def exhaustion_ticks(self) -> int:
        """Number of ticks the queue was empty when an action was demanded (`FR-INF-012`).

        Returns:
            (int) Starved ticks.
        """
        return self._exhaustion_ticks

    @property
    def exhaustion_ratio(self) -> float:
        """Fraction of consume ticks that were starved (`FR-INF-012`).

        Returns:
            (float) `exhaustion_ticks / total_ticks`, or 0.0 before any tick.
        """
        if self._total_ticks == 0:
            return 0.0
        return self._exhaustion_ticks / self._total_ticks

    @property
    def residual_series(self) -> tuple[int, ...]:
        """The recent per-tick queue-size backlog, oldest first (`FR-INF-020`).

        Returns:
            (tuple[int, ...]) Queue sizes recorded at each tick, within the window.
        """
        return tuple(self._residual_series)

    def tick(self, queue_size: int) -> bool:
        """Record one consume tick given the queue size seen before the consume.

        Args:
            queue_size: The action-queue size at the start of this tick. `0` means
                the tick is starved; the queue had no action to hand the consumer.

        Returns:
            (bool) True when this tick was starved (queue empty), else False.
        """
        self._total_ticks += 1
        self._residual_series.append(queue_size)
        exhausted = queue_size == 0
        if exhausted:
            self._exhaustion_ticks += 1
        return exhausted

    def reset(self) -> None:
        """Clear all counters and the residual series (episode or backend switch)."""
        self._total_ticks = 0
        self._exhaustion_ticks = 0
        self._residual_series.clear()
