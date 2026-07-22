"""The event ring: a lossless pre/post telemetry window around a collision event.

WP-2C-09. Where the WP-2A-05 audit ring dumps the retained window *at* a safe-stop,
this ring must keep the seconds before **and after** an event (`02b` §3 WP-2C-09,
`12` FR-SAF-065). It does not re-implement the audit ring — it reuses it: an
`EventRingBuffer` may be bound to an `AuditRingBuffer`, and one `on_safety_event`
call snapshots both, so a collision yields a single coherent dump carrying the
command/decision window (audit) beside the physical-telemetry window (this ring),
under one `LatchReason` and one timestamp.

Reuse and ownership: this ring holds no latch and drives no torque. It is a passive
recorder. The detection-only latch source is the Wave-1 `CollisionGuard`
(`backend.actuation`); the harness wires that guard's latch callback to
`on_safety_event`, exactly as it wires the audit ring. Recording is unconditional
and is not the detection activation gate (WP-2C-02 owns that) — a band whose
detection default is OFF still records, because a window you did not keep is a
window you cannot analyse.

Lossless pre/post: the pre window is a rolling retention deque, evicted by horizon;
a within-horizon sample dropped by capacity pressure is the one real loss vector and
is counted, not swallowed (`dropped_within_window`). The post window is fed straight
into the armed capture, bypassing eviction, so it cannot be lost while the caller
keeps feeding. A dump that lost a within-window sample reports `lossless=False`;
`require_lossless` turns that into the WP-2C-09 negative branch (RETRY_WITH_VARIANT:
recompute capacity/sample rate) rather than letting a short window pass as complete.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from backend.audit import AuditDump, AuditRingBuffer
from backend.event_ring.constants import (
    DEFAULT_POST_EVENT_SEC,
    DEFAULT_PRE_EVENT_SEC,
)
from backend.event_ring.errors import EventRingLossError
from backend.event_ring.sample import TelemetrySample
from ops.cancel.scheduler import LatchReason


@dataclass(frozen=True)
class EventDump:
    """An immutable pre/post telemetry window around one event, plus its command peer.

    Attributes:
        pre: Samples retained from before the event, oldest first, spanning at least
            the configured pre-event window when the ring lost nothing.
        post: Samples captured after the event, oldest first, spanning at least the
            configured post-event window once the capture completed.
        trigger: The latch reason that armed the capture (collision, lease expiry, …).
        audit: The paired audit-ring dump (WP-2A-05) taken under the same trigger, or
            None when this ring was not bound to an audit ring.
        dropped_within_window: Samples the ring lost to capacity pressure while they
            still belonged in the retention window — the ring's self-report of loss.
        complete: Whether the post window filled to at least its configured span.
    """

    pre: tuple[TelemetrySample, ...]
    post: tuple[TelemetrySample, ...]
    trigger: LatchReason
    audit: AuditDump | None
    dropped_within_window: int
    complete: bool

    @property
    def samples(self) -> tuple[TelemetrySample, ...]:
        """The whole window, pre followed by post, oldest first."""
        return self.pre + self.post

    @property
    def lossless(self) -> bool:
        """Whether the window is complete and no within-window sample was lost.

        Returns:
            (bool) True when the post window filled and the ring dropped no sample
            that belonged in the retention window over its lifetime.
        """
        return self.complete and self.dropped_within_window == 0

    def pre_span_sec(self) -> float:
        """The monotonic span the pre window covers, newest minus oldest.

        Returns:
            (float) Span in seconds; 0.0 when fewer than two pre samples.
        """
        if len(self.pre) < 2:
            return 0.0
        return self.pre[-1].at - self.pre[0].at

    def post_span_sec(self) -> float:
        """The monotonic span the post window covers, newest minus oldest.

        Returns:
            (float) Span in seconds; 0.0 when fewer than two post samples.
        """
        if len(self.post) < 2:
            return 0.0
        return self.post[-1].at - self.post[0].at

    def require_lossless(self) -> None:
        """Raise if this dump is not a complete, lossless window.

        The harness calls this before trusting a dump for post-event analysis. A
        lossy or incomplete window is the WP-2C-09 negative branch, not a usable
        record.

        Raises:
            EventRingLossError: If the window is incomplete or lost a within-window
                sample.
        """
        if not self.lossless:
            raise EventRingLossError(
                "event window is not lossless: "
                f"complete={self.complete}, dropped_within_window={self.dropped_within_window} "
                "— recompute capacity/sample rate (RETRY_WITH_VARIANT)"
            )


class EventCapture:
    """One armed event accumulating its post window until the span is covered.

    Ownership: returned by `EventRingBuffer.on_safety_event` and fed by the ring's
    subsequent `record` calls until `complete`. The pre window is snapshotted at arm
    time, so it is fixed the instant the event fires; the post window grows as ticks
    arrive. The caller holds this handle, checks `complete`, then reads `dump`.
    """

    def __init__(
        self,
        pre: tuple[TelemetrySample, ...],
        trigger: LatchReason,
        post_event_sec: float,
        audit: AuditDump | None,
        dropped_at_arm: int,
    ) -> None:
        """Arm a capture around an event.

        Args:
            pre: The pre-window snapshot taken at arm time, oldest first.
            trigger: The latch reason that armed this capture.
            post_event_sec: Seconds of post-event telemetry to collect before the
                capture is complete.
            audit: The paired audit dump under the same trigger, or None.
            dropped_at_arm: The ring's within-window loss count at arm time.
        """
        self._pre = pre
        self._trigger = trigger
        self._event_at = trigger.latched_at
        self._post_event_sec = post_event_sec
        self._audit = audit
        self._dropped_at_arm = dropped_at_arm
        self._post: list[TelemetrySample] = []
        self._complete = False

    @property
    def complete(self) -> bool:
        """Whether the post window has reached its configured span."""
        return self._complete

    def feed(self, sample: TelemetrySample, dropped_now: int) -> bool:
        """Offer one post-event sample to this capture.

        Args:
            sample: The tick to add, if it falls after the event.
            dropped_now: The ring's current within-window loss count, folded in so a
                loss during post collection is reflected in the dump.

        Returns:
            (bool) True when this sample completed the capture.
        """
        if self._complete or sample.at <= self._event_at:
            return False
        self._post.append(sample)
        self._dropped_at_arm = max(self._dropped_at_arm, dropped_now)
        if sample.at >= self._event_at + self._post_event_sec:
            self._complete = True
            return True
        return False

    @property
    def dump(self) -> EventDump:
        """The dump for this capture, complete or not.

        Returns:
            (EventDump) The pre/post window with the trigger, audit peer, and loss
            count. `complete` is False until the post span is covered.
        """
        return EventDump(
            pre=self._pre,
            post=tuple(self._post),
            trigger=self._trigger,
            audit=self._audit,
            dropped_within_window=self._dropped_at_arm,
            complete=self._complete,
        )


class EventRingBuffer:
    """A rolling telemetry ring that arms a lossless pre/post capture on an event.

    Ownership: holds the rolling pre-window deque, the running within-window loss
    count, and the set of currently armed captures. Optionally bound to a WP-2A-05
    `AuditRingBuffer` so one safe-stop dumps both rings coherently. Holds no latch
    and no CAN handle — on an event it is called, exactly as the audit ring is.
    """

    def __init__(
        self,
        capacity: int,
        pre_event_sec: float = DEFAULT_PRE_EVENT_SEC,
        post_event_sec: float = DEFAULT_POST_EVENT_SEC,
        audit_ring: AuditRingBuffer | None = None,
    ) -> None:
        """Configure the window and, optionally, the audit ring to dump alongside.

        Args:
            capacity: Maximum samples retained in the rolling pre window. Sized for
                the pre-event span at the loop rate; when it is smaller than that
                span holds, a retained sample is lost and counted. The real rate is
                hardware-deferred, so capacity is a caller input, not a constant.
            pre_event_sec: Seconds of pre-event telemetry to retain.
            post_event_sec: Seconds of post-event telemetry to collect after an event.
            audit_ring: A WP-2A-05 audit ring to snapshot under the same trigger, so
                the event dump carries the command/decision window beside telemetry.
        """
        self._capacity = capacity
        self._pre_event_sec = pre_event_sec
        self._post_event_sec = post_event_sec
        self._audit_ring = audit_ring
        self._samples: deque[TelemetrySample] = deque()
        self._dropped_within_window = 0
        self._active: list[EventCapture] = []

    @property
    def capacity(self) -> int:
        """The rolling pre-window capacity in samples."""
        return self._capacity

    @property
    def dropped_within_window(self) -> int:
        """Samples lost to capacity pressure while still within the retention window.

        Zero for a ring whose capacity holds the pre-event span at the feed rate. A
        non-zero value is loss the WP-2C-09 negative branch exists for; it is exposed
        so a caller can recompute capacity or sample rate rather than discovering the
        loss only in a short dump.
        """
        return self._dropped_within_window

    @property
    def retained(self) -> tuple[TelemetrySample, ...]:
        """The rolling pre-window contents, oldest first."""
        return tuple(self._samples)

    def record(self, sample: TelemetrySample) -> None:
        """Append one tick, evict the stale tail, and feed any armed captures.

        Samples must arrive in non-decreasing `at` order; the pre-window snapshot a
        later event takes depends on that ordering.

        Args:
            sample: The tick's telemetry.
        """
        self._samples.append(sample)
        self._evict()
        completed = [
            capture for capture in self._active if capture.feed(sample, self._dropped_within_window)
        ]
        if completed:
            done = set(map(id, completed))
            self._active = [capture for capture in self._active if id(capture) not in done]

    def on_safety_event(self, reason: LatchReason) -> EventCapture:
        """Arm a pre/post capture around a safe-stop or collision.

        Snapshots the pre window immediately and, when bound, dumps the audit ring
        under the same reason so the two windows share one trigger and timestamp.
        Recording continues; the capture fills its post window from subsequent ticks.

        Args:
            reason: The latch reason for the stop, carried into the dump.

        Returns:
            (EventCapture) The armed capture; read `complete`, then `dump`.
        """
        event_at = reason.latched_at
        pre = tuple(
            sample
            for sample in self._samples
            if event_at - self._pre_event_sec <= sample.at <= event_at
        )
        audit = self._audit_ring.on_safety_event(reason) if self._audit_ring is not None else None
        capture = EventCapture(
            pre=pre,
            trigger=reason,
            post_event_sec=self._post_event_sec,
            audit=audit,
            dropped_at_arm=self._dropped_within_window,
        )
        self._active.append(capture)
        return capture

    def _evict(self) -> None:
        """Drop samples beyond the horizon, then count any capacity loss.

        Horizon eviction (older than the pre-event span behind the newest sample) is
        ordinary retention, not loss. Only a sample still inside that span, dropped
        because capacity is exhausted, is a lost within-window sample.
        """
        newest_at = self._samples[-1].at
        while self._samples and newest_at - self._samples[0].at > self._pre_event_sec:
            self._samples.popleft()
        while len(self._samples) > self._capacity:
            self._samples.popleft()
            self._dropped_within_window += 1
