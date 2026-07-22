"""The per-episode quality report WP-3B-12 ③ assembles, and its provisional gate.

`build_report` turns one episode's recorded frames and capture sidecar into a
`QualityReport` — the seven `metrics` measures plus the frame count and duration. The
per-frame input is a `FrameSample`, the shape the WP-3B-11 recorder holds in its episode
buffer; this band consumes that buffer (and, for crash detection, the parquet the
recorder writes) rather than re-recording anything.

`evaluate` compares a report against thresholds the *caller* supplies. It bakes in none:
`02b` §5.2 WP-3B-12 ⑥ fixes the quality-gate bar as `[결정필요]`, to be measured on this
hardware then regression-locked, and forbids adopting ALOHA's 84% success-rate figure.
A metric with no supplied threshold reports `UNSET`, never a fabricated pass.

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
    JerkStats,
    LoopTiming,
    StdFloorStats,
    camera_drop_stats,
    can_drop_stats,
    jerk_stats,
    loop_timing,
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
    kept minimal — only the fields the seven metrics read — so the quality band depends
    on the recorded data, not on the recorder's implementation types.

    Attributes:
        frame_index: The 0-based frame position, the sidecar join key.
        timestamp: The frame timestamp in seconds (`CTR-PRIM@v1` synthetic-grid domain).
        action: The position-only action, `<motor>.pos` -> degrees.
        observation_state: The interleaved `observation.state` vector.
        can_stale: Whether the recorder flagged this frame as a CAN drop whose state was
            reused from the previous frame; False when the recorder supplies no flag.
    """

    frame_index: int
    timestamp: float
    action: Mapping[str, float]
    observation_state: tuple[float, ...]
    can_stale: bool = False


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
        duration_s: The wall span from first to last frame timestamp.
        loop: Loop-rate and jitter.
        missing: The missing-sample count.
        can_drop: CAN-drop exposure.
        camera_drop: Per-slot camera-drop exposure.
        jerk: The position-command jerk.
        std_floor: The observation-state std floor.
    """

    episode_index: int
    frame_count: int
    duration_s: float
    loop: LoopTiming
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
            "loop": {
                "rate_hz": self.loop.rate_hz,
                "mean_period_s": self.loop.mean_period_s,
                "jitter_std_s": self.loop.jitter_std_s,
                "max_deviation_s": self.loop.max_deviation_s,
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
    thresholds: QualityThresholds | None = None,
) -> QualityReport:
    """Assemble the quality report for one episode.

    Args:
        frames: The episode's frames in order, from the recorder buffer.
        sidecar: The episode's capture sidecar (`CTR-CAP@v1`).
        config: The recorder configuration the episode was recorded under.
        thresholds: The provisional floor for the std-floor flagging; other gate
            comparisons happen in `evaluate`.

    Returns:
        (QualityReport) The seven measures plus frame count and duration.
    """
    names = action_names(config.bimanual)
    positions = [[float(frame.action[name]) for name in names] for frame in frames]
    states = [frame.observation_state for frame in frames]
    timestamps = [frame.timestamp for frame in frames]
    flags = [frame.can_stale for frame in frames]
    floor = thresholds.min_std_floor if thresholds is not None else None
    duration = (timestamps[-1] - timestamps[0]) if len(timestamps) >= 2 else 0.0
    return QualityReport(
        episode_index=sidecar.episode_index,
        frame_count=len(frames),
        duration_s=duration,
        loop=loop_timing(timestamps),
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
    would be worse than an absent one.

    Args:
        report: The report to grade.
        thresholds: The provisional bars; any None field yields `UNSET` for that metric.

    Returns:
        (dict[str, GateOutcome]) One outcome per metric.
    """
    can_total = report.can_drop.flagged_frames + report.can_drop.suspected_stale_frames
    return {
        "loop_rate": _at_least(report.loop.rate_hz, thresholds.min_loop_rate_hz),
        "jitter": _at_most(report.loop.jitter_std_s, thresholds.max_jitter_std_s),
        "missing": _at_most(report.missing, thresholds.max_missing_samples),
        "can_drop": _at_most(can_total, thresholds.max_can_drop_frames),
        "camera_drop": _at_most(report.total_camera_drop(), thresholds.max_camera_drop_frames),
        "jerk": _at_most(report.jerk.max_abs, thresholds.max_jerk),
        "std_floor": _at_least(report.std_floor.min_std, thresholds.min_std_floor),
    }


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
