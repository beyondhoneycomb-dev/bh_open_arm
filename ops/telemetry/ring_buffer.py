"""The preceding-30-second diagnostic ring buffer (`14` FR-OPS-024).

The window is a contract with an exact boundary, so eviction is defined precisely: a sample
at time `t` is retained at query time `now` iff `now - t <= window`. The boundary sample —
exactly `window` seconds old — is *kept*; anything older is dropped. Getting this off by an
epsilon would make the "preceding 30 s" claim quietly false, which is why the boundary is
pinned by its own test rather than left implicit.

The buffer is bounded twice over: by the time window and by `RING_MAX_SAMPLES`. A ring that
grew without bound under a fast producer would not be a ring; the count cap is the floor of
that guarantee independent of the arrival rate.

Time is always passed in, never read from a clock here. A pure, clock-free structure is the
only way the boundary test can place a sample *exactly* on the edge and assert the outcome.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ops.telemetry.constants import DIAGNOSTIC_WINDOW_S, RING_MAX_SAMPLES
from ops.telemetry.structured_log import LogRecord


@dataclass(frozen=True)
class DiagnosticSample:
    """A diagnostic record tagged with the monotonic time it entered the ring.

    Attributes:
        t: Monotonic time in seconds used for windowing (not the record's own ns clock,
            so callers may drive the window from an injected clock in tests).
        record: The structured record retained for replay.
    """

    t: float
    record: LogRecord

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable form for the crash spool and MCAP.

        Returns:
            (dict[str, Any]) `{t, record}` with the record inlined.
        """
        return {"t": self.t, "record": self.record.to_dict()}


class DiagnosticRingBuffer:
    """A time-windowed, count-bounded ring of diagnostic samples.

    Ownership/threading: single-producer. The control loop appends on its own thread; the
    supervisor never mutates it, it only reads a spooled snapshot.
    """

    def __init__(
        self,
        window_s: float = DIAGNOSTIC_WINDOW_S,
        max_samples: int = RING_MAX_SAMPLES,
    ) -> None:
        self.m_window_s = window_s
        self.m_max_samples = max_samples
        self.m_samples: deque[DiagnosticSample] = deque()

    def append(self, t: float, record: LogRecord) -> None:
        """Add a sample at time `t` and evict anything now outside the window.

        Args:
            t: Monotonic seconds for this sample; must be non-decreasing across calls.
            record: The structured record to retain.
        """
        self.m_samples.append(DiagnosticSample(t=t, record=record))
        self._evict(t)

    def _evict(self, now: float) -> None:
        """Drop samples older than the window, then enforce the count cap.

        Args:
            now: Current monotonic seconds; the right edge of the retention window.
        """
        window = self.m_window_s
        samples = self.m_samples
        while samples and (now - samples[0].t) > window:
            samples.popleft()
        while len(samples) > self.m_max_samples:
            samples.popleft()

    def snapshot(self, now: float | None = None) -> tuple[DiagnosticSample, ...]:
        """Return the retained samples, optionally re-evicting against `now` first.

        Passing `now` matters at read time: a producer that went quiet still has stale
        samples in the deque, and the window must be re-applied against the read instant,
        not the last append instant.

        Args:
            now: If given, evict against this time before snapshotting.

        Returns:
            (tuple[DiagnosticSample, ...]) Retained samples, oldest first.
        """
        if now is not None:
            self._evict(now)
        return tuple(self.m_samples)

    def coverage(self, now: float | None = None) -> tuple[float, float] | None:
        """Return the `(oldest_t, newest_t)` the buffer currently covers.

        Args:
            now: If given, evict against this time first.

        Returns:
            (tuple[float, float] | None) The covered span, or None when empty.
        """
        snap = self.snapshot(now)
        if not snap:
            return None
        return (snap[0].t, snap[-1].t)


class RingSink:
    """A `LogSink` functor that appends every record to a ring at an injected clock time.

    Adapts the ring buffer to the structured logger's sink protocol. It is a named functor
    rather than a lambda so the binding of `ring` and `now_fn` is explicit and typed.
    """

    def __init__(self, ring: DiagnosticRingBuffer, now_fn: Callable[[], float]) -> None:
        self.m_ring = ring
        self.m_now_fn = now_fn

    def __call__(self, record: LogRecord) -> None:
        """Append `record` to the ring stamped with the current clock time.

        Args:
            record: The record emitted by the logger.
        """
        self.m_ring.append(self.m_now_fn(), record)
