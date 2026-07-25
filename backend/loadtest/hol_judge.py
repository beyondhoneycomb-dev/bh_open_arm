"""The HOL judge — the two things a load run must show, and the one it must not.

`CG-5-05a` and `CG-5-05b` are different kinds of judgment and this module keeps them
apart on purpose:

  * `CG-5-05a` is "the measurement exists". It produces the p50/p95/p99 round-trip
    latency of the control classes (telemetry, command) under load and renders NO
    pass/fail — `NFR-GUI-004`/`NFR-GUI-005` are both decision-needed and SPINE §2-6
    forbids a target before the measurement. A judge that returned PASS here would be
    inventing the very threshold the plan withholds.

  * `CG-5-05b` is "the ordering holds". At link saturation the camera class must
    degrade first while telemetry and command are protected. This IS decidable now,
    because it is an order, not a number: camera frames are shed and the control
    classes are not. If a control class degrades before the camera, the single-WS
    premise (U-4) is broken and the verdict is INVERTED — a FAIL, per the negative
    branch, and the fix is the backpressure policy, not resurrecting D-2.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.loadtest.constants import ROUNDTRIP_PERCENTILES, ROUNDTRIP_TAIL_PERCENTILE
from backend.loadtest.harness import LoadRun
from backend.loadtest.stats import percentile
from contracts.ws.schema import BACKPRESSURE_PROTECTED_FRAMES, WsFrameType

# The classes whose round-trip latency the load test reports (`NFR-GUI-012` H2:
# telemetry and command must not be pushed behind the camera).
CONTROL_CLASSES = (WsFrameType.TELEMETRY, WsFrameType.COMMAND)


@dataclass(frozen=True)
class LatencyProfile:
    """The measured round-trip latency distribution of one control class.

    Attributes:
        frame_type: The class measured.
        sample_count: How many delivered frames the percentiles were taken over.
        percentiles_sec: Percentile label (e.g. 99.0) to latency in seconds.
    """

    frame_type: WsFrameType
    sample_count: int
    percentiles_sec: dict[float, float]

    @property
    def tail_sec(self) -> float:
        """The tail (p99) latency, in seconds."""
        return self.percentiles_sec[ROUNDTRIP_TAIL_PERCENTILE]


@dataclass(frozen=True)
class RoundTripMeasurement:
    """The `CG-5-05a` output: control-class latency measured, no pass line rendered.

    Attributes:
        profiles: One `LatencyProfile` per control class that carried traffic.
        no_threshold_note: The explicit statement that this is a measurement, not a
            verdict — carried so a reader cannot mistake a produced number for a
            confirmed pass line.
    """

    profiles: dict[WsFrameType, LatencyProfile]
    no_threshold_note: str

    def tail_sec(self, frame_type: WsFrameType) -> float:
        """The p99 latency of one control class, seconds."""
        return self.profiles[frame_type].tail_sec


_NO_THRESHOLD_NOTE = (
    "measurement only: NFR-GUI-004/NFR-GUI-005 are decision-needed and SPINE §2-6 "
    "forbids a target before measurement, so this WP renders no pass/fail on latency"
)


def measure_roundtrip(run: LoadRun) -> RoundTripMeasurement:
    """Produce the control-class round-trip latency measurement (`CG-5-05a`).

    Args:
        run: The completed load run.

    Returns:
        (RoundTripMeasurement) The per-class percentiles, with no threshold applied.

    Raises:
        ValueError: If a control class delivered no frames — a measurement that never
            produced a sample is not a measurement, and is refused rather than
            reported as zero.
    """
    profiles: dict[WsFrameType, LatencyProfile] = {}
    for frame_type in CONTROL_CLASSES:
        result = run.result(frame_type)
        if not result.latencies_sec:
            raise ValueError(
                f"control class {frame_type.value!r} delivered no frames; the p99 cannot "
                "be produced and is not reported as zero"
            )
        profiles[frame_type] = LatencyProfile(
            frame_type=frame_type,
            sample_count=len(result.latencies_sec),
            percentiles_sec={
                pct: percentile(result.latencies_sec, pct) for pct in ROUNDTRIP_PERCENTILES
            },
        )
    return RoundTripMeasurement(profiles=profiles, no_threshold_note=_NO_THRESHOLD_NOTE)


class OrderingVerdict(Enum):
    """Whether the camera degraded first (protected) or a control class did (inverted)."""

    PROTECTED = "protected"
    INVERTED = "inverted"


@dataclass(frozen=True)
class OrderingJudgment:
    """The `CG-5-05b` output: did the camera degrade first under saturation?

    Attributes:
        verdict: PROTECTED when the camera is shed and the control classes are not;
            INVERTED when a control class is shed or lost (the FAIL branch).
        camera_dropped: Camera frames shed under backpressure — must be positive for
            the judgment to mean anything (a run that never saturated cannot judge
            ordering).
        protected_dropped: Total frames dropped across the protected classes — must be
            zero for PROTECTED.
        reason: A human-readable account of the verdict.
    """

    verdict: OrderingVerdict
    camera_dropped: int
    protected_dropped: int
    reason: str

    @property
    def protected(self) -> bool:
        """Whether the ordering held (camera degraded first)."""
        return self.verdict is OrderingVerdict.PROTECTED


def judge_ordering(run: LoadRun) -> OrderingJudgment:
    """Judge whether the camera degraded first while the control classes were protected.

    The judgment reads the CTR-WS protected set (lease/command/telemetry) rather than
    naming classes here, so "which classes must be protected" has one definition. The
    verdict is INVERTED — a FAIL — if any protected class lost a frame, or if the
    camera was never shed (no saturation means no evidence of ordering).

    Args:
        run: The completed load run.

    Returns:
        (OrderingJudgment) The ordering verdict with its supporting counts.
    """
    camera_dropped = run.result(WsFrameType.CAMERA).dropped
    protected_dropped = sum(
        run.result(frame_type).dropped for frame_type in BACKPRESSURE_PROTECTED_FRAMES
    )

    if protected_dropped > 0:
        return OrderingJudgment(
            verdict=OrderingVerdict.INVERTED,
            camera_dropped=camera_dropped,
            protected_dropped=protected_dropped,
            reason=(
                f"{protected_dropped} protected-class frame(s) were dropped — a control "
                "class degraded, which inverts the single-WS priority (fix backpressure, "
                "do not resurrect D-2)"
            ),
        )
    if camera_dropped == 0:
        return OrderingJudgment(
            verdict=OrderingVerdict.INVERTED,
            camera_dropped=0,
            protected_dropped=0,
            reason=(
                "the camera was never shed — the link did not saturate, so the ordering "
                "invariant was not exercised and cannot be claimed"
            ),
        )
    return OrderingJudgment(
        verdict=OrderingVerdict.PROTECTED,
        camera_dropped=camera_dropped,
        protected_dropped=0,
        reason=(
            f"camera degraded first ({camera_dropped} preview frame(s) shed) while every "
            "protected class kept all its frames"
        ),
    )
