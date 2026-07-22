"""Stage-2 batch-transcode worker (`02b` §6.2 WP-3B-05 ②③).

The two-stage design records lossless originals during the episode and transcodes
them *after* the episode ends, on a worker that is not the recording path — so
starting the next episode never waits on the previous episode's transcode
(`07` NFR-REC-005). This module is that worker.

Threading contract: one background daemon thread drains a queue of transcode jobs.
`submit` runs on the caller (recording) thread and only enqueues, so it returns in
constant time and cannot block the next episode. The injected `transcode_fn` runs
on the worker thread alone; the codec it uses is out of scope here — the production
SW/HW codec matrix (`libsvtav1`, `h264_nvenc`) and its real-time factor are the
resource-exclusive WP-3C-02 measurement (`PG-STO-001`).

Backpressure is a warning, not a block (`07` NFR-REC-005). The originals are already
on disk, so if transcoding falls behind, the outstanding count grows and this warns
once it passes `encoder_queue_maxsize` (~1 s of work) — the disk-fill it foreshadows
is caught by the F14 monitor / R-20, and blocking here would defeat the whole point
of the separate worker.
"""

from __future__ import annotations

import math
import threading
import time
import warnings
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from backend.sensing.encoding.constants import ENCODER_QUEUE_MAXSIZE_DEFAULT
from backend.sensing.encoding.rawstore import RawEpisodeStore, RawStreamRef


class BackpressureWarning(UserWarning):
    """Raised when outstanding transcode work passes the encoder queue threshold.

    A warning, never an exception: the originals are safe on disk and the recording
    must not be blocked, so this surfaces the encoder falling behind without
    stopping collection (`07` NFR-REC-005).
    """


def percentile(values: Sequence[int], p: float) -> float:
    """Return the p-th percentile of a sample by linear interpolation.

    The `07` NFR-REC-005 latency figures are p50/p95, so this is the shared
    percentile both the save-latency and transcode-latency recorders use. Linear
    interpolation between ranks matches the common statistical definition and is
    stable for the small samples a test drives.

    Args:
        values: The samples (e.g. nanosecond durations).
        p: The percentile in [0, 100].

    Returns:
        (float) The interpolated percentile value.

    Raises:
        ValueError: If `values` is empty or `p` is outside [0, 100].
    """
    if not values:
        raise ValueError("percentile of an empty sample is undefined")
    if not 0.0 <= p <= 100.0:
        raise ValueError(f"percentile p must be in [0, 100], got {p}")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (p / 100.0) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(ordered[low])
    fraction = rank - low
    return float(ordered[low]) + (float(ordered[high]) - float(ordered[low])) * fraction


class LatencyRecorder:
    """A thread-safe series of nanosecond durations with percentile read-out.

    Ownership: shared between the recording thread (which records save latency) and
    the worker thread (which records transcode latency), so every access is locked.
    """

    def __init__(self) -> None:
        """Start an empty recorder."""
        self._samples: list[int] = []
        self._lock = threading.Lock()

    def record(self, duration_ns: int) -> None:
        """Append one duration sample.

        Args:
            duration_ns: A wall-clock duration in nanoseconds.
        """
        with self._lock:
            self._samples.append(duration_ns)

    def samples(self) -> tuple[int, ...]:
        """Return a snapshot of the recorded samples."""
        with self._lock:
            return tuple(self._samples)

    def count(self) -> int:
        """Return the number of recorded samples."""
        with self._lock:
            return len(self._samples)

    def percentile(self, p: float) -> float:
        """Return the p-th percentile of the recorded samples.

        Args:
            p: The percentile in [0, 100].

        Returns:
            (float) The interpolated percentile in nanoseconds.
        """
        with self._lock:
            snapshot = tuple(self._samples)
        return percentile(snapshot, p)


@dataclass(frozen=True)
class StreamTranscode:
    """The transcode outcome for one camera stream of an episode.

    Attributes:
        stream: The stream that was transcoded.
        raw_frame_count: The number of originals stage 1 recorded for the stream.
        encoded_frame_count: The number of frames the transcode produced, counted
            back from the output — the `NFR-CAM-007` frame-count integrity figure.
        output_path: The transcoded artifact (or the originals directory when the
            production codec for this stream kind is deferred).
    """

    stream: RawStreamRef
    raw_frame_count: int
    encoded_frame_count: int
    output_path: Path

    @property
    def frame_count_matches(self) -> bool:
        """Whether the transcode preserved the frame count (`NFR-CAM-007` ①)."""
        return self.raw_frame_count == self.encoded_frame_count


@dataclass(frozen=True)
class TranscodeResult:
    """The transcode outcome for one whole episode.

    Attributes:
        episode_index: The episode this result belongs to.
        streams: Per-stream transcode outcomes.
    """

    episode_index: int
    streams: tuple[StreamTranscode, ...] = field(default_factory=tuple)

    @property
    def frame_counts_match(self) -> bool:
        """Whether every stream preserved its frame count (`NFR-CAM-007` ①)."""
        return all(stream.frame_count_matches for stream in self.streams)


@dataclass(frozen=True)
class TranscodeJob:
    """One episode's transcode work: its originals and where the output goes.

    Attributes:
        store: The stage-1 original store for the episode.
        streams: The camera streams to transcode.
        output_dir: The directory the transcoded artifacts are written to.
    """

    store: RawEpisodeStore
    streams: tuple[RawStreamRef, ...]
    output_dir: Path

    @property
    def episode_index(self) -> int:
        """The episode this job transcodes."""
        return self.store.episode_index


@dataclass(frozen=True)
class BackpressureEvent:
    """A single crossing of the encoder backpressure threshold.

    Attributes:
        episode_index: The episode whose submission crossed the threshold.
        outstanding: The outstanding-transcode count at that moment.
        threshold: The `encoder_queue_maxsize` the count exceeded.
    """

    episode_index: int
    outstanding: int
    threshold: int


TranscodeFn = Callable[[TranscodeJob], TranscodeResult]
BackpressureHandler = Callable[[BackpressureEvent], None]


class TranscodeWorker:
    """A single-threaded, non-blocking batch-transcode worker.

    Ownership: owns one daemon thread that is the sole caller of `transcode_fn`.
    `submit` (the recording thread) only enqueues; it never runs a transcode, so it
    cannot block the next episode. Call `close` to drain the current job and join.
    """

    def __init__(
        self,
        transcode_fn: TranscodeFn,
        encoder_queue_maxsize: int = ENCODER_QUEUE_MAXSIZE_DEFAULT,
        on_backpressure: BackpressureHandler | None = None,
    ) -> None:
        """Start the worker thread.

        Args:
            transcode_fn: The transcode to run per job, on the worker thread only.
            encoder_queue_maxsize: The outstanding-work threshold above which a
                backpressure warning is raised.
            on_backpressure: Optional handler invoked on each threshold crossing.
        """
        self._transcode_fn = transcode_fn
        self._maxsize = encoder_queue_maxsize
        self._on_backpressure = on_backpressure
        self._queue: deque[TranscodeJob] = deque()
        self._results: dict[int, TranscodeResult] = {}
        self._failures: dict[int, BaseException] = {}
        self._latency_ns: list[int] = []
        self._outstanding = 0
        self._backpressure_events = 0
        self._stopping = False
        self._cond = threading.Condition()
        self._thread = threading.Thread(target=self._run, name="transcode-worker", daemon=True)
        self._thread.start()

    @property
    def thread_ident(self) -> int | None:
        """The worker thread's identity, for asserting transcode ran off-path."""
        return self._thread.ident

    @property
    def outstanding(self) -> int:
        """The count of submitted-but-not-completed jobs (queued plus in-progress)."""
        with self._cond:
            return self._outstanding

    @property
    def backpressure_events(self) -> int:
        """The number of times submission crossed the backpressure threshold."""
        with self._cond:
            return self._backpressure_events

    def submit(self, job: TranscodeJob) -> None:
        """Enqueue an episode's transcode and return without running it.

        This is the recording-thread entry point. It appends the job, bumps the
        outstanding count, and — only if that count now exceeds the threshold —
        raises the backpressure warning on this thread. It never blocks on the
        transcode, which is what keeps the next episode unblocked.

        Args:
            job: The episode transcode to enqueue.
        """
        with self._cond:
            self._queue.append(job)
            self._outstanding += 1
            outstanding = self._outstanding
            over_threshold = outstanding > self._maxsize
            if over_threshold:
                self._backpressure_events += 1
            self._cond.notify_all()
        if over_threshold:
            self._emit_backpressure(
                BackpressureEvent(job.episode_index, outstanding, self._maxsize)
            )

    def _emit_backpressure(self, event: BackpressureEvent) -> None:
        """Warn and notify a handler that the backpressure threshold was crossed."""
        warnings.warn(
            BackpressureWarning(
                f"transcode backpressure: {event.outstanding} episodes outstanding exceeds "
                f"encoder_queue_maxsize {event.threshold}; originals are accumulating on disk"
            ),
            stacklevel=3,
        )
        if self._on_backpressure is not None:
            self._on_backpressure(event)

    def _run(self) -> None:
        """Drain the queue on the worker thread until closed."""
        while True:
            with self._cond:
                while not self._queue and not self._stopping:
                    self._cond.wait()
                if self._stopping and not self._queue:
                    return
                job = self._queue.popleft()
            self._run_one(job)

    def _run_one(self, job: TranscodeJob) -> None:
        """Run one transcode, recording its latency and surviving a failure.

        A transcode that raises must not kill the worker thread — the remaining
        episodes still need transcoding — so the exception is captured and the
        outstanding count is released either way, keeping `wait_idle` correct.
        """
        start_ns = time.perf_counter_ns()
        result: TranscodeResult | None = None
        failure: BaseException | None = None
        try:
            result = self._transcode_fn(job)
        except Exception as exc:  # worker must survive a bad transcode (threading contract)
            failure = exc
        elapsed_ns = time.perf_counter_ns() - start_ns
        with self._cond:
            if result is not None:
                self._results[job.episode_index] = result
                self._latency_ns.append(elapsed_ns)
            if failure is not None:
                self._failures[job.episode_index] = failure
            self._outstanding -= 1
            self._cond.notify_all()

    def transcode_latency_ns(self) -> tuple[int, ...]:
        """A snapshot of per-episode transcode durations, in nanoseconds."""
        with self._cond:
            return tuple(self._latency_ns)

    def transcode_percentile(self, p: float) -> float:
        """The p-th percentile of transcode completion latency (`07` NFR-REC-005).

        Args:
            p: The percentile in [0, 100].

        Returns:
            (float) The interpolated latency in nanoseconds.
        """
        return percentile(self.transcode_latency_ns(), p)

    def result(self, episode_index: int) -> TranscodeResult | None:
        """The transcode result for an episode, or None if not yet complete.

        Args:
            episode_index: The episode to look up.

        Returns:
            (TranscodeResult | None) The result, or None.
        """
        with self._cond:
            return self._results.get(episode_index)

    def failure(self, episode_index: int) -> BaseException | None:
        """The exception a failed transcode raised for an episode, or None.

        Args:
            episode_index: The episode to look up.

        Returns:
            (BaseException | None) The captured exception, or None.
        """
        with self._cond:
            return self._failures.get(episode_index)

    def wait_idle(self, timeout: float | None = None) -> bool:
        """Block until no transcode is outstanding, or the timeout elapses.

        A test helper: production code never waits on the worker (that is the point).

        Args:
            timeout: Seconds to wait, or None to wait indefinitely.

        Returns:
            (bool) True when the worker went idle, False on timeout.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._cond:
            while self._outstanding > 0:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                self._cond.wait(remaining)
            return True

    def close(self, timeout: float | None = None) -> None:
        """Stop the worker after the current queue drains, then join its thread.

        Args:
            timeout: Seconds to wait for the thread to join, or None.
        """
        with self._cond:
            self._stopping = True
            self._cond.notify_all()
        self._thread.join(timeout)
