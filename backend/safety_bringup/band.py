"""The collision-detection loop bandwidth verdict (`12` NFR-SAF-001, acceptance ⑪).

The 1 kHz detection loop with a p99 jitter under 200 us holds only under pattern A (16
frames per cycle). Under pattern B (32 frames per cycle, the LeRobot default) the CAN-FD
budget caps the loop at 625 Hz, and NFR-SAF-001 requires the loop to be clamped to that
ceiling, flagged as degraded, and shown with its effective latency.

The ceiling is further bounded by `f_max_python`, which `WP-1-04` publishes as
*provisional* under PG-RT-001a. This verdict therefore consumes a provisional figure and is
stale when `PG-RT-001b:PASS` re-derives it (`06` CI-11c) — the trigger the plan row's
`재도출 = PG-RT-001b:PASS` declares. It is named here at the point of consumption so the
dependency on the provisional bound is not silent.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.rtbench.constants import FINAL_GATE as PG_RT_001B
from backend.rtbench.fmax import FMax
from backend.safety_bringup.constants import (
    DETECTION_LOOP_PATTERN_B_CEILING_HZ,
    DETECTION_LOOP_TARGET_HZ,
    FRAMES_PER_CYCLE_PATTERN_A,
    FRAMES_PER_CYCLE_PATTERN_B,
)

# The staleness trigger this verdict declares: it rests on WP-1-04's provisional
# f_max_python, which PG-RT-001b re-derives on the real rig (`06` CI-11c).
STALE_ON = f"{PG_RT_001B}:PASS"


class FramePattern:
    """The two CAN read patterns (`15` §2.1). Pattern A reads 16 frames/cycle, B reads 32."""

    A = FRAMES_PER_CYCLE_PATTERN_A
    B = FRAMES_PER_CYCLE_PATTERN_B


@dataclass(frozen=True)
class DetectionBand:
    """The resolved detection-loop bandwidth and its degradation state (acceptance ⑪).

    Attributes:
        frames_per_cycle: The frame pattern in effect (16 == A, 32 == B).
        target_hz: The requested loop rate — 1 kHz for the detection loop.
        effective_hz: The rate actually admitted after the pattern and f_max bounds.
        clamped: Whether the pattern-B 625 Hz ceiling clamped the target.
        degraded: Whether the loop runs below its 1 kHz target (the FR-SAF-001b demotion).
        effective_latency_sec: One over the effective rate — the latency the UI must show.
        provisional: Whether the bounding f_max is provisional (always true when consumed).
    """

    frames_per_cycle: int
    target_hz: float
    effective_hz: float
    clamped: bool
    degraded: bool
    effective_latency_sec: float
    provisional: bool


def resolve_detection_band(frames_per_cycle: int, fmax: FMax) -> DetectionBand:
    """Resolve the detection loop bandwidth for a frame pattern and provisional f_max (⑪).

    Under pattern A the 1 kHz target stands, bounded only by f_max. Under pattern B the
    target is clamped to the 625 Hz CAN-FD ceiling, then bounded by f_max; the loop is
    marked degraded and its effective latency is reported.

    Args:
        frames_per_cycle: The CAN read pattern (16 == A, 32 == B).
        fmax: The `WP-1-04` combined f_max figure (provisional via f_max_python).

    Returns:
        (DetectionBand) The admitted bandwidth with its clamp/degrade flags and latency.
    """
    target = DETECTION_LOOP_TARGET_HZ
    if frames_per_cycle >= FRAMES_PER_CYCLE_PATTERN_B:
        ceiling = DETECTION_LOOP_PATTERN_B_CEILING_HZ
        clamped = True
    else:
        ceiling = target
        clamped = False

    effective = min(ceiling, target)
    f_max_hz = fmax.f_max_hz
    if f_max_hz is not None:
        effective = min(effective, f_max_hz)

    return DetectionBand(
        frames_per_cycle=frames_per_cycle,
        target_hz=target,
        effective_hz=effective,
        clamped=clamped,
        degraded=effective < target,
        effective_latency_sec=1.0 / effective if effective > 0 else float("inf"),
        provisional=fmax.provisional,
    )
