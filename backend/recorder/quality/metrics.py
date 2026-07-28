"""The quality metrics WP-3B-12 ③ computes over one recorded episode (`02b` §5.2).

Six measures, each a pure function of a recorded series: the cycle-time distribution
from the recorder's own loop instants, missing-sample count from the frame-index gaps,
CAN drop from the observation stream, camera drop from the capture sidecar, jerk from the
position command, and the standard-deviation floor across the state channels.

The cycle time is measured from `CLOCK_MONOTONIC` instants the recorder stamps per loop
iteration, never from the dataset `timestamp`: that column is the `CTR-PRIM@v1`
`frame_index / fps` grid, so differencing it can only ever return the configured fps with
zero spread — a number that looks like a measurement and is the input read back.

The CAN-drop measure exists because of a specific hazard the plan names (`02b` §5.2
WP-3B-12 ③): the recorder's `_batch_refresh` reuses the last state when a CAN batch is
missed, so a dropped sample enters the dataset looking like a fresh one. This module
surfaces both signals — the recorder's own drop flag when it supplies one (authoritative),
and a heuristic count of consecutive-identical state rows (suspected stale reuse) — so
the drop is visible rather than hidden inside a plausible-looking sample.

Camera drop reuses the frozen `CTR-CAP@v1` primitives (`slot_frame_numbers`,
`frame_numbers_continuous`): a gap in the device frame counter is a dropped frame, and
that definition lives once, in the capture contract, not a second time here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.recorder.quality.constants import (
    CYCLE_TIME_PERCENTILE_P50,
    CYCLE_TIME_PERCENTILE_P95,
    CYCLE_TIME_PERCENTILE_P99,
    JERK_UNIT,
    MIN_SAMPLES_FOR_JERK,
    MIN_SAMPLES_FOR_RATE,
    MIN_SELECTABLE_FPS,
    NANOS_PER_SECOND,
)
from contracts.capture import CameraSlotKey, CaptureSidecar
from contracts.capture.schema import frame_numbers_continuous, slot_frame_numbers


class CycleTimeError(ValueError):
    """A cycle-time input the report refuses to reduce to a number.

    Two causes. A target rate below `MIN_SELECTABLE_FPS` has no period to compare a cycle
    against. A cycle instant that does not advance is broken data rather than a slow cycle
    — `CLOCK_MONOTONIC` cannot run backwards or stand still across two loop iterations —
    and differencing it would publish a negative or infinite rate as a measurement.
    """


@dataclass(frozen=True)
class CycleTimeStats:
    """The recording loop's measured cycle time, against the target the operator chose.

    Every measured field is None when the recorder stamped no cycle instants, never 0.0:
    a zero would read as a loop that ran at no hertz with perfect jitter, which is a
    fabricated result standing in for an absent one. `target_fps` and `interval_count` are
    always present, so an unmeasured episode still records what it was aiming at.

    Attributes:
        target_fps: The operator-selected rate the cycles were compared against.
        interval_count: How many cycle intervals were measured; n instants give n-1.
        p50_s: The median cycle time in seconds.
        p95_s: The 95th-percentile cycle time in seconds.
        p99_s: The 99th-percentile cycle time in seconds.
        max_s: The longest single cycle in seconds.
        jitter_std_s: The standard deviation of the cycle time in seconds.
        missed_target_intervals: Cycles that ran longer than the target period.
        missed_target_share: Those cycles over `interval_count`. Reported, never graded:
            NORM-013 refuses a pass line on it.
    """

    target_fps: int
    interval_count: int
    p50_s: float | None
    p95_s: float | None
    p99_s: float | None
    max_s: float | None
    jitter_std_s: float | None
    missed_target_intervals: int | None
    missed_target_share: float | None

    def achieved_rate_hz(self) -> float | None:
        """The rate the median cycle achieves, or None when nothing was measured.

        Derived rather than stored, so the achieved rate and the median it comes from can
        never drift into being two different claims about one loop.
        """
        if self.p50_s is None:
            return None
        return 1.0 / self.p50_s


@dataclass(frozen=True)
class CanDropStats:
    """CAN-drop exposure over the observation stream.

    Attributes:
        flagged_frames: Frames the recorder itself marked as a CAN drop (authoritative).
        suspected_stale_frames: Frames whose state exactly repeats the previous frame's,
            the heuristic signature of a `_batch_refresh` reuse.
        total_frames: The frame count the two counts are measured against.
    """

    flagged_frames: int
    suspected_stale_frames: int
    total_frames: int


@dataclass(frozen=True)
class CameraDropStats:
    """Per-slot camera-drop exposure from the capture sidecar.

    Attributes:
        slot: The camera slot key.
        missing_rows: Frames whose sidecar row carried no capture for this slot.
        frame_number_gaps: Frames the device counter skipped between kept frames.
    """

    slot: str
    missing_rows: int
    frame_number_gaps: int


@dataclass(frozen=True)
class JerkStats:
    """The third time-derivative of the position command.

    Attributes:
        max_abs: The largest absolute jerk over any channel and time.
        rms: The root-mean-square jerk across every channel and time.
        unit: The magnitude unit (`deg/s^3`).
    """

    max_abs: float
    rms: float
    unit: str


@dataclass(frozen=True)
class StdFloorStats:
    """The standard-deviation floor across the observation-state channels.

    A channel whose value barely moves over an episode has a near-zero std — a stuck or
    dead channel the report must flag. The floor threshold is supplied by the caller and
    left provisional; none is baked in (`02b` §5.2 WP-3B-12 ⑥).

    Attributes:
        min_std: The smallest per-channel standard deviation.
        per_channel_std: The standard deviation of every channel, in channel order.
        below_floor: Channel indices whose std falls below the supplied floor; empty
            when no floor was given.
    """

    min_std: float
    per_channel_std: tuple[float, ...]
    below_floor: tuple[int, ...]


def validate_target_fps(target_fps: int) -> int:
    """Return the operator's target rate, refusing only a rate that has no cycle period.

    NORM-013 declines a lower bound on the achieved loop rate and requires instead that
    the operator be able to lower the target, so the sole refusal here is arithmetic:
    below one frame per second there is no period for a cycle to overrun. No ceiling
    either — a target the machine cannot hold is reported as missed, not rejected.

    Args:
        target_fps: The operator-selected recording rate.

    Returns:
        (int) The same rate, once it is usable as a period.

    Raises:
        CycleTimeError: When the rate falls below `MIN_SELECTABLE_FPS`.
    """
    if target_fps < MIN_SELECTABLE_FPS:
        raise CycleTimeError(
            f"target fps {target_fps} is below {MIN_SELECTABLE_FPS} and has no cycle period"
        )
    return target_fps


def cycle_time_stats(cycle_mono_ns: Sequence[int], target_fps: int) -> CycleTimeStats:
    """Reduce a loop's cycle instants to the distribution NORM-013 requires reporting.

    The target is validated before the instants are read, so an episode that measured
    nothing still refuses a rate with no period rather than reporting against one.

    A cycle misses the target when `interval_ns * target_fps > NANOS_PER_SECOND`. That
    integer form is exact; dividing out a period in nanoseconds would leave a cycle landing
    on the target sitting on the wrong side of a rounded float, and the usual repair for
    that is a tolerance — a bar under another name, which is what the ruling refuses.

    Percentiles come from `np.percentile`'s default linear interpolation. The repo holds
    three percentile helpers and two of them already disagree on the definition
    (`backend/loadtest/stats.py:14` and `backend/torque_bringup/stop_latency.py:74` take
    nearest-rank, `backend/sensing/encoding/worker.py:46` interpolates), so there is no
    canon to reuse; numpy is already this module's dependency and the encoding helper's
    definition is the one it matches.

    Args:
        cycle_mono_ns: `CLOCK_MONOTONIC` nanosecond instants, one per loop cycle, in order.
        target_fps: The operator-selected target rate.

    Returns:
        (CycleTimeStats) The percentiles, spread and missed-target share over n-1 intervals
            — the share's denominator is intervals, not frames, because one frame has no
            cycle time. All-None with `interval_count` 0 below two instants.

    Raises:
        CycleTimeError: When the target has no period, or an instant does not advance.
    """
    validate_target_fps(target_fps)
    if len(cycle_mono_ns) < MIN_SAMPLES_FOR_RATE:
        return CycleTimeStats(
            target_fps=target_fps,
            interval_count=0,
            p50_s=None,
            p95_s=None,
            p99_s=None,
            max_s=None,
            jitter_std_s=None,
            missed_target_intervals=None,
            missed_target_share=None,
        )
    intervals = np.diff(np.asarray(cycle_mono_ns, dtype=np.int64))
    if int(np.min(intervals)) <= 0:
        raise CycleTimeError(
            f"cycle instants must advance; found a gap of {int(np.min(intervals))} ns"
        )
    missed = int(np.count_nonzero(intervals * target_fps > NANOS_PER_SECOND))
    interval_count = int(intervals.size)
    return CycleTimeStats(
        target_fps=target_fps,
        interval_count=interval_count,
        p50_s=_nanos_to_seconds(np.percentile(intervals, CYCLE_TIME_PERCENTILE_P50)),
        p95_s=_nanos_to_seconds(np.percentile(intervals, CYCLE_TIME_PERCENTILE_P95)),
        p99_s=_nanos_to_seconds(np.percentile(intervals, CYCLE_TIME_PERCENTILE_P99)),
        max_s=_nanos_to_seconds(np.max(intervals)),
        jitter_std_s=_nanos_to_seconds(np.std(intervals)),
        missed_target_intervals=missed,
        missed_target_share=missed / interval_count,
    )


def missing_samples(frame_indices: Sequence[int]) -> int:
    """Count the samples missing from a contiguous frame-index span.

    Args:
        frame_indices: The recorded frame indices, in any order.

    Returns:
        (int) How many indices between the smallest and largest are absent; 0 for an
            empty or single-frame series.
    """
    if len(frame_indices) < MIN_SAMPLES_FOR_RATE:
        return 0
    present = set(frame_indices)
    span = max(present) - min(present) + 1
    return span - len(present)


def can_drop_stats(states: Sequence[Sequence[float]], flags: Sequence[bool]) -> CanDropStats:
    """Expose CAN drops over the observation stream.

    Args:
        states: Per-frame `observation.state` vectors, in frame order.
        flags: Per-frame recorder-supplied CAN-drop flags, aligned with `states`.

    Returns:
        (CanDropStats) The authoritative flagged count and the heuristic
            consecutive-identical count, over the same frame total.
    """
    total = len(states)
    flagged = sum(1 for flag in flags if flag)
    suspected = sum(
        1
        for earlier, later in zip(states, states[1:], strict=False)
        if tuple(earlier) == tuple(later)
    )
    return CanDropStats(
        flagged_frames=flagged, suspected_stale_frames=suspected, total_frames=total
    )


def camera_drop_stats(sidecar: CaptureSidecar) -> tuple[CameraDropStats, ...]:
    """Expose per-slot camera drops from the capture sidecar.

    Args:
        sidecar: The episode capture sidecar.

    Returns:
        (tuple[CameraDropStats, ...]) One record per slot, missing rows plus the device
            frame-counter gaps, using the frozen `CTR-CAP@v1` continuity definition.
    """
    stats: list[CameraDropStats] = []
    for slot in sidecar.slots():
        missing_rows = sum(1 for row in sidecar.rows if row.slots.get(slot) is None)
        numbers = slot_frame_numbers(sidecar, slot)
        gaps = (
            0
            if frame_numbers_continuous(numbers)
            else sum(
                max(0, later - earlier - 1)
                for earlier, later in zip(numbers, numbers[1:], strict=False)
            )
        )
        stats.append(
            CameraDropStats(
                slot=_slot_name(slot), missing_rows=missing_rows, frame_number_gaps=gaps
            )
        )
    return tuple(stats)


def jerk_stats(positions: Sequence[Sequence[float]], timestamps: Sequence[float]) -> JerkStats:
    """Compute the third time-derivative of the per-channel position command.

    Args:
        positions: Per-frame position vectors (`<motor>.pos`), in frame order.
        timestamps: Per-frame timestamps in seconds, aligned with `positions`.

    Returns:
        (JerkStats) Zeroed below four frames, where a third derivative is undefined.
    """
    if len(positions) < MIN_SAMPLES_FOR_JERK:
        return JerkStats(max_abs=0.0, rms=0.0, unit=JERK_UNIT)
    matrix = np.asarray(positions, dtype=float)
    time = np.asarray(timestamps, dtype=float)
    derivative = matrix
    for _ in range(3):
        derivative = np.gradient(derivative, time, axis=0)
    return JerkStats(
        max_abs=float(np.max(np.abs(derivative))),
        rms=float(np.sqrt(np.mean(np.square(derivative)))),
        unit=JERK_UNIT,
    )


def std_floor_stats(states: Sequence[Sequence[float]], floor: float | None = None) -> StdFloorStats:
    """Compute the per-channel standard-deviation floor across the state channels.

    Args:
        states: Per-frame `observation.state` vectors, in frame order.
        floor: The provisional threshold below which a channel is flagged as stuck; when
            None no channel is flagged (`02b` §5.2 WP-3B-12 ⑥ leaves the bar `[결정필요]`).

    Returns:
        (StdFloorStats) The minimum std, the per-channel std, and the flagged indices.
    """
    if not states:
        return StdFloorStats(min_std=0.0, per_channel_std=(), below_floor=())
    matrix = np.asarray(states, dtype=float)
    per_channel = np.std(matrix, axis=0)
    below = () if floor is None else tuple(int(i) for i in np.nonzero(per_channel < floor)[0])
    return StdFloorStats(
        min_std=float(np.min(per_channel)),
        per_channel_std=tuple(float(value) for value in per_channel),
        below_floor=below,
    )


def _nanos_to_seconds(value: np.floating[Any] | np.integer[Any]) -> float:
    """Convert a nanosecond magnitude from the cycle-time arithmetic into report seconds."""
    return float(value) / NANOS_PER_SECOND


def _slot_name(slot: CameraSlotKey) -> str:
    """Return a slot's string key for reporting, tolerating a plain-string slot."""
    return slot.value if isinstance(slot, CameraSlotKey) else str(slot)
