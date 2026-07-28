"""The per-episode quality report WP-3B-12 ③ assembles, and its provisional gate.

`build_report` turns one episode's recorded frames and capture sidecar into a
`QualityReport` — the six `metrics` measures plus the frame count and duration. The
per-frame input is a `FrameSample`, the shape the WP-3B-11 recorder holds in its episode
buffer; this band consumes that buffer (and, for crash detection, the parquet the
recorder writes) rather than re-recording anything.

`evaluate` compares a report against thresholds the *caller* supplies. It bakes in none:
`02b` §5.2 WP-3B-12 ⑥ fixes the quality-gate bar as `[결정필요]`, to be measured on this
hardware then regression-locked, and forbids adopting ALOHA's 84% success-rate figure.
A metric with no supplied threshold reports `UNSET`, never a fabricated pass — and so does
a metric with no measurement behind it, whatever threshold was supplied.

`QualityThresholds` carries no bar on the missed-target share, and that absence is the
point: NORM-013 requires the share to be reported and refuses to make it a pass line, so
grading it here would rebuild the floor the ruling declined to set.

Channel roles come from the frozen `CTR-REC@v1` name helpers (`action_names`,
`observation_state_names`): the position command feeding the jerk measure is the
`action` block, addressed by name, never a hardcoded slice.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from backend.recorder.quality.metrics import (
    CameraDropStats,
    CanDropStats,
    CycleTimeError,
    CycleTimeStats,
    JerkStats,
    StdFloorStats,
    camera_drop_stats,
    can_drop_stats,
    cycle_time_stats,
    jerk_stats,
    missing_samples,
    std_floor_stats,
)
from contracts.capture import CaptureSidecar
from contracts.recorder import RecorderConfig, action_names


class GateOutcome(StrEnum):
    """The verdict a single metric earns against its threshold."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNSET = "UNSET"


@dataclass(frozen=True)
class FrameSample:
    """One recorded frame, the unit the quality metrics consume.

    This is the shape the WP-3B-11 recorder holds per frame in its episode buffer. It is
    kept minimal — only the fields the six metrics read — so the quality band depends
    on the recorded data, not on the recorder's implementation types.

    Attributes:
        frame_index: The 0-based frame position, the sidecar join key.
        timestamp: The frame timestamp in seconds (`CTR-PRIM@v1` synthetic-grid domain).
        action: The position-only action, `<motor>.pos` -> degrees.
        observation_state: The interleaved `observation.state` vector.
        can_stale: Whether the recorder flagged this frame as a CAN drop whose state was
            reused from the previous frame; False when the recorder supplies no flag.
        cycle_mono_ns: The `CLOCK_MONOTONIC` nanosecond instant the recorder stamped at the
            top of this frame's loop cycle; None when the recorder stamps none, and then
            None on every frame of the episode — `build_report` refuses a partly stamped
            one. `timestamp` cannot stand in for it — that is the synthetic
            `frame_index / fps` grid, so differencing it returns the configured fps rather
            than the achieved one.
    """

    frame_index: int
    timestamp: float
    action: Mapping[str, float]
    observation_state: tuple[float, ...]
    can_stale: bool = False
    cycle_mono_ns: int | None = None


@dataclass(frozen=True)
class QualityThresholds:
    """Provisional quality-gate thresholds, every one caller-supplied.

    None means "no bar declared" — the corresponding metric evaluates to `UNSET`, not a
    default pass. `02b` §5.2 WP-3B-12 ⑥ leaves every bar `[결정필요]`; this type is the
    seam a measured, regression-locked set of values is injected through later.

    Attributes:
        min_loop_rate_hz: The lowest acceptable loop rate.
        max_jitter_std_s: The largest acceptable inter-frame jitter.
        max_missing_samples: The most missing samples tolerated.
        max_can_drop_frames: The most CAN-drop frames tolerated (flagged plus suspected).
        max_camera_drop_frames: The most camera-drop frames tolerated across all slots.
        max_jerk: The largest acceptable absolute jerk.
        min_std_floor: The smallest per-channel std a live channel must exceed.
    """

    min_loop_rate_hz: float | None = None
    max_jitter_std_s: float | None = None
    max_missing_samples: int | None = None
    max_can_drop_frames: int | None = None
    max_camera_drop_frames: int | None = None
    max_jerk: float | None = None
    min_std_floor: float | None = None


@dataclass(frozen=True)
class QualityReport:
    """The quality measures for one recorded episode.

    Attributes:
        episode_index: The episode measured.
        frame_count: How many frames the episode holds.
        duration_s: The nominal episode length, first to last grid timestamp.
        cycle_time: The loop's measured cycle-time distribution against the operator's
            target rate; present on every report, measured only when the recorder
            supplied cycle instants.
        missing: The missing-sample count.
        can_drop: CAN-drop exposure.
        camera_drop: Per-slot camera-drop exposure.
        jerk: The position-command jerk.
        std_floor: The observation-state std floor.
    """

    episode_index: int
    frame_count: int
    duration_s: float
    cycle_time: CycleTimeStats
    missing: int
    can_drop: CanDropStats
    camera_drop: tuple[CameraDropStats, ...]
    jerk: JerkStats
    std_floor: StdFloorStats

    def total_camera_drop(self) -> int:
        """Sum of missing rows and frame-counter gaps across every slot."""
        return sum(stat.missing_rows + stat.frame_number_gaps for stat in self.camera_drop)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe mapping for the on-disk sidecar."""
        return {
            "episode_index": self.episode_index,
            "frame_count": self.frame_count,
            "duration_s": self.duration_s,
            "cycle_time": {
                "target_fps": self.cycle_time.target_fps,
                "interval_count": self.cycle_time.interval_count,
                "p50_s": self.cycle_time.p50_s,
                "p95_s": self.cycle_time.p95_s,
                "p99_s": self.cycle_time.p99_s,
                "max_s": self.cycle_time.max_s,
                "jitter_std_s": self.cycle_time.jitter_std_s,
                "achieved_rate_hz": self.cycle_time.achieved_rate_hz(),
                "missed_target_intervals": self.cycle_time.missed_target_intervals,
                "missed_target_share": self.cycle_time.missed_target_share,
            },
            "missing_samples": self.missing,
            "can_drop": {
                "flagged_frames": self.can_drop.flagged_frames,
                "suspected_stale_frames": self.can_drop.suspected_stale_frames,
                "total_frames": self.can_drop.total_frames,
            },
            "camera_drop": [
                {
                    "slot": stat.slot,
                    "missing_rows": stat.missing_rows,
                    "frame_number_gaps": stat.frame_number_gaps,
                }
                for stat in self.camera_drop
            ],
            "jerk": {"max_abs": self.jerk.max_abs, "rms": self.jerk.rms, "unit": self.jerk.unit},
            "std_floor": {
                "min_std": self.std_floor.min_std,
                "per_channel_std": list(self.std_floor.per_channel_std),
                "below_floor": list(self.std_floor.below_floor),
            },
            "thresholds": "provisional (02b §5.2 WP-3B-12 ⑥ [결정필요])",
        }


def build_report(
    frames: Sequence[FrameSample],
    sidecar: CaptureSidecar,
    config: RecorderConfig,
    target_fps: int,
    thresholds: QualityThresholds | None = None,
) -> QualityReport:
    """Assemble the quality report for one episode.

    `target_fps` has no default. A default would be the 30 the ruling declined to bless,
    and every report built without a second thought would then carry it as if the operator
    had chosen it.

    Args:
        frames: The episode's frames in order, from the recorder buffer.
        sidecar: The episode's capture sidecar (`CTR-CAP@v1`).
        config: The recorder configuration the episode was recorded under.
        target_fps: The rate the operator recorded at, which the cycle times are compared
            against.
        thresholds: The provisional floor for the std-floor flagging; other gate
            comparisons happen in `evaluate`.

    Returns:
        (QualityReport) The six measures plus frame count and duration.

    Raises:
        CycleTimeError: When `target_fps` has no cycle period, when a stamped cycle instant
            does not advance, or when only some of the frames carry one.
    """
    names = action_names(config.bimanual)
    positions = [[float(frame.action[name]) for name in names] for frame in frames]
    states = [frame.observation_state for frame in frames]
    timestamps = [frame.timestamp for frame in frames]
    flags = [frame.can_stale for frame in frames]
    instants = _cycle_instants(frames)
    floor = thresholds.min_std_floor if thresholds is not None else None
    duration = (timestamps[-1] - timestamps[0]) if len(timestamps) >= 2 else 0.0
    return QualityReport(
        episode_index=sidecar.episode_index,
        frame_count=len(frames),
        duration_s=duration,
        cycle_time=cycle_time_stats(instants, target_fps),
        missing=missing_samples([frame.frame_index for frame in frames]),
        can_drop=can_drop_stats(states, flags),
        camera_drop=camera_drop_stats(sidecar),
        jerk=jerk_stats(positions, timestamps),
        std_floor=std_floor_stats(states, floor),
    )


def evaluate(report: QualityReport, thresholds: QualityThresholds) -> dict[str, GateOutcome]:
    """Grade a report against caller-supplied thresholds.

    A metric with no threshold set evaluates to `UNSET` — never a default pass, because
    the bar is genuinely undetermined (`02b` §5.2 WP-3B-12 ⑥) and a fabricated green
    would be worse than an absent one. The same holds from the other side: a metric with
    no measurement is `UNSET` whatever bar was supplied. Substituting 0.0 for an unstamped
    cycle time turns one absent number into a FAIL on the rate and a PASS on the jitter,
    two verdicts about a loop nobody timed.

    Args:
        report: The report to grade.
        thresholds: The provisional bars; any None field yields `UNSET` for that metric.

    Returns:
        (dict[str, GateOutcome]) One outcome per metric.
    """
    can_total = report.can_drop.flagged_frames + report.can_drop.suspected_stale_frames
    return {
        "loop_rate": _at_least_measured(
            report.cycle_time.achieved_rate_hz(), thresholds.min_loop_rate_hz
        ),
        "jitter": _at_most_measured(report.cycle_time.jitter_std_s, thresholds.max_jitter_std_s),
        "missing": _at_most(report.missing, thresholds.max_missing_samples),
        "can_drop": _at_most(can_total, thresholds.max_can_drop_frames),
        "camera_drop": _at_most(report.total_camera_drop(), thresholds.max_camera_drop_frames),
        "jerk": _at_most(report.jerk.max_abs, thresholds.max_jerk),
        "std_floor": _at_least(report.std_floor.min_std, thresholds.min_std_floor),
    }


def _cycle_instants(frames: Sequence[FrameSample]) -> list[int]:
    """Return the episode's cycle instants, refusing a partly stamped one.

    Keeping only the stamped frames and differencing them as if they were consecutive turns
    a gap of N frames into one long cycle, which then lands in the percentiles and the
    missed-target share as a measured value. An episode is stamped throughout or not at all.

    Args:
        frames: The episode's frames in order.

    Returns:
        (list[int]) Every frame's cycle instant, or empty when no frame carries one.

    Raises:
        CycleTimeError: When some frames carry a cycle instant and others do not.
    """
    stamps = [frame.cycle_mono_ns for frame in frames]
    instants = [stamp for stamp in stamps if stamp is not None]
    if instants and len(instants) != len(stamps):
        raise CycleTimeError(
            f"{len(stamps) - len(instants)} of {len(stamps)} frames carry no cycle instant; "
            "the stamped rest are not consecutive cycles"
        )
    return instants


def _at_least(value: float, threshold: float | None) -> GateOutcome:
    """Pass when the measured value meets or exceeds the threshold; UNSET when none."""
    if threshold is None:
        return GateOutcome.UNSET
    return GateOutcome.PASS if value >= threshold else GateOutcome.FAIL


def _at_most(value: float, threshold: float | None) -> GateOutcome:
    """Pass when the measured value stays at or below the threshold; UNSET when none."""
    if threshold is None:
        return GateOutcome.UNSET
    return GateOutcome.PASS if value <= threshold else GateOutcome.FAIL


def _at_least_measured(value: float | None, threshold: float | None) -> GateOutcome:
    """`_at_least` for a metric that may be unmeasured; an absent value is UNSET."""
    if value is None:
        return GateOutcome.UNSET
    return _at_least(value, threshold)


def _at_most_measured(value: float | None, threshold: float | None) -> GateOutcome:
    """`_at_most` for a metric that may be unmeasured; an absent value is UNSET."""
    if value is None:
        return GateOutcome.UNSET
    return _at_most(value, threshold)
