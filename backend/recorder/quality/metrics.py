"""The quality metrics WP-3B-12 ③ computes over one recorded episode (`02b` §5.2).

Seven measures, each a pure function of a recorded series: loop rate and jitter from
the frame timestamps, missing-sample count from the frame-index gaps, CAN drop from the
observation stream, camera drop from the capture sidecar, jerk from the position
command, and the standard-deviation floor across the state channels.

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

import numpy as np

from backend.recorder.quality.constants import (
    JERK_UNIT,
    MIN_SAMPLES_FOR_JERK,
    MIN_SAMPLES_FOR_RATE,
)
from contracts.capture import CameraSlotKey, CaptureSidecar
from contracts.capture.schema import frame_numbers_continuous, slot_frame_numbers


@dataclass(frozen=True)
class LoopTiming:
    """Loop-rate and jitter derived from the frame timestamps.

    Attributes:
        rate_hz: The recording loop rate, one over the median inter-frame interval.
        mean_period_s: The mean inter-frame interval in seconds.
        jitter_std_s: The standard deviation of the inter-frame interval.
        max_deviation_s: The largest absolute departure of any interval from the mean.
    """

    rate_hz: float
    mean_period_s: float
    jitter_std_s: float
    max_deviation_s: float


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


def loop_timing(timestamps: Sequence[float]) -> LoopTiming:
    """Compute loop rate and jitter from a frame-timestamp series.

    Args:
        timestamps: Per-frame timestamps in seconds, in frame order.

    Returns:
        (LoopTiming) Zeroed when fewer than two frames or a non-positive interval makes
            the rate undefined.
    """
    if len(timestamps) < MIN_SAMPLES_FOR_RATE:
        return LoopTiming(rate_hz=0.0, mean_period_s=0.0, jitter_std_s=0.0, max_deviation_s=0.0)
    periods = np.diff(np.asarray(timestamps, dtype=float))
    mean_period = float(np.mean(periods))
    median_period = float(np.median(periods))
    rate = 1.0 / median_period if median_period > 0.0 else 0.0
    return LoopTiming(
        rate_hz=rate,
        mean_period_s=mean_period,
        jitter_std_s=float(np.std(periods)),
        max_deviation_s=float(np.max(np.abs(periods - mean_period))),
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


def _slot_name(slot: CameraSlotKey) -> str:
    """Return a slot's string key for reporting, tolerating a plain-string slot."""
    return slot.value if isinstance(slot, CameraSlotKey) else str(slot)
