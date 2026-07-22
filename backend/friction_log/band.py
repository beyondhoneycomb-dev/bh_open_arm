"""Achieved logging band — frequency, jitter, and the provisional tick-rate compare.

From a captured frame sequence this computes the *achieved* logging frequency and its
jitter, purely from the frame timestamps, so the analysis runs on synthetic ticks with
no hardware. What it will NOT do is present those numbers as the final band: the tick
rate and `f_max_python` come from `PG-RT-001a`, which is provisional (a synthetic GIL
load) and hardware-deferred here — `PG-RT-001b` finalises it on the rig. So the compare
of logging rate against tick rate and `f_max_python` (acceptance ④) is marked provisional
and re-run through `reverify`; only the shape of the computation is fixed here.

The one thing NOT deferred for pattern A is the structural bound: pattern A emits exactly
one frame per tick from inside the tick, so the logging rate cannot exceed the tick rate
by construction (acceptance ⑤). `logging_did_not_outrun_ticks` states that as a
frame-count-vs-tick-count check, which needs no real frequency.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import pstdev

from backend.friction_log.frame import LogFrame

# Tap identifiers recorded on the band, so a reader can tell a scheduler-internal capture
# from a manual RX capture without inspecting the call site.
PATTERN_SCHEDULER_TAP = "A"
PATTERN_MANUAL_RX = "B"


@dataclass(frozen=True)
class LoggingStats:
    """Frequency and jitter measured from a frame sequence's timestamps.

    Attributes:
        frame_count: Number of frames observed.
        duration_sec: Span from first to last frame timestamp, seconds.
        achieved_hz: Mean logging frequency over the span, or 0.0 when undefined.
        max_interval_sec: Largest gap between consecutive frames, seconds.
        jitter_sec: Population standard deviation of the inter-frame intervals.
    """

    frame_count: int
    duration_sec: float
    achieved_hz: float
    max_interval_sec: float
    jitter_sec: float


def logging_stats(frames: tuple[LogFrame, ...]) -> LoggingStats:
    """Measure achieved logging frequency and jitter from a frame sequence.

    Args:
        frames: Captured frames, in capture order.

    Returns:
        (LoggingStats) Frequency and jitter derived from the frame timestamps. With
        fewer than two frames there is no interval and every rate field is 0.0.
    """
    if len(frames) < 2:
        return LoggingStats(len(frames), 0.0, 0.0, 0.0, 0.0)
    times = [frame.at for frame in frames]
    intervals = [later - earlier for earlier, later in zip(times, times[1:], strict=False)]
    duration = times[-1] - times[0]
    achieved = (len(frames) - 1) / duration if duration > 0.0 else 0.0
    return LoggingStats(
        frame_count=len(frames),
        duration_sec=duration,
        achieved_hz=achieved,
        max_interval_sec=max(intervals),
        jitter_sec=pstdev(intervals) if len(intervals) > 1 else 0.0,
    )


@dataclass(frozen=True)
class AchievedBand:
    """The achieved logging band plus the targets it is compared against.

    Attributes:
        pattern: Which tap produced the log (`A` scheduler-internal, `B` manual RX).
        stats: The measured frequency and jitter.
        tick_rate_hz: The achieved scheduler tick rate, or None when unmeasured here.
        f_max_python_hz: The `PG-RT-001a` figure, or None when unmeasured here.
        provisional: True whenever a real target is absent — the compare cannot be final
            without `PG-RT-001b`, so a synthetic-log band must never be read as a
            `PG-FRIC-001`-grade result.
    """

    pattern: str
    stats: LoggingStats
    tick_rate_hz: float | None
    f_max_python_hz: float | None
    provisional: bool


def achieved_band(
    pattern: str,
    frames: tuple[LogFrame, ...],
    tick_rate_hz: float | None = None,
    f_max_python_hz: float | None = None,
) -> AchievedBand:
    """Build the achieved-band record for a capture.

    `tick_rate_hz` and `f_max_python_hz` default to None because they are produced by
    `PG-RT-001a` on the rig, which is hardware-deferred here; a band built without them
    is marked provisional so its frequency is never mistaken for a final measurement.

    Args:
        pattern: The tap identifier (`PATTERN_SCHEDULER_TAP` or `PATTERN_MANUAL_RX`).
        frames: Captured frames, in capture order.
        tick_rate_hz: The achieved tick rate, when a real measurement is supplied.
        f_max_python_hz: The `f_max_python` figure, when a real measurement is supplied.

    Returns:
        (AchievedBand) The band, provisional unless both real targets are supplied.
    """
    provisional = tick_rate_hz is None or f_max_python_hz is None
    return AchievedBand(
        pattern=pattern,
        stats=logging_stats(frames),
        tick_rate_hz=tick_rate_hz,
        f_max_python_hz=f_max_python_hz,
        provisional=provisional,
    )


def logging_did_not_outrun_ticks(frame_count: int, tick_count: int) -> bool:
    """Whether pattern-A logging stayed at or below the tick rate (acceptance ⑤).

    Pattern A emits one frame per tick from inside the tick, so the frame count must
    never exceed the tick count. A frame count above the tick count would mean the logger
    produced frames the scheduler did not — i.e. it drove the bus itself.

    Args:
        frame_count: Frames the sink captured.
        tick_count: Ticks the scheduler executed.

    Returns:
        (bool) True when logging did not outrun ticks.
    """
    return frame_count <= tick_count
