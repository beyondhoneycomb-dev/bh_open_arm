"""The five-step mitigation ladder and the dual diagnosis of a frame timeout.

Two obligations of WP-3B-02 live here. First, a block is not a dead end: when a
configuration exceeds budget the operator is offered an ordered ladder of remedies,
cheapest-first, so the same ladder `PG-CAM-001` applies on real hardware
(`02b` WP-3C-01) is already the one the offline block hands back (FR-CAM-012/013).
Second, the RealSense `"Frame did not arrive in time"` symptom has two independent
causes — the bandwidth budget and bus power — and a diagnosis naming only one sends
the operator down the wrong path (FR-CAM-071).

The ladder is data, not behaviour: it neither reads a camera nor mutates a
configuration. It states what to try and why, and a downstream UI or the block's
error surfaces it. That keeps it fully verifiable offline.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.sensing.bandwidth.constants import (
    CAUSE_BANDWIDTH,
    CAUSE_POWER,
    FRAME_TIMEOUT_SYMPTOM,
    MITIGATION_STEP_COUNT,
)


@dataclass(frozen=True)
class MitigationStep:
    """One rung of the mitigation ladder.

    Attributes:
        order: 1-based position; the ladder is tried in this order, cheapest first.
        action: The remedy to apply.
        rationale: Why it lowers the budget, tied to the formula the block uses.
    """

    order: int
    action: str
    rationale: str


# The ladder `06` §5 Q7 fixes and `02b` WP-3C-01 spells out: negotiate a compressed
# format (lower Bpp on the wire) → move a camera to another controller (lower a
# single controller's shared sum) → turn depth off (drop the second stream) → lower
# fps → lower resolution. Cheapest-first: the earlier rungs preserve resolution.
MITIGATION_LADDER: tuple[MitigationStep, ...] = (
    MitigationStep(
        order=1,
        action="Confirm the camera negotiated a compressed format (MJPEG) rather than raw YUYV",
        rationale="a compressed stream lowers effective bytes-per-pixel, cutting W×H×Bpp×8×fps",
    ),
    MitigationStep(
        order=2,
        action="Redistribute cameras across USB controllers so no one controller carries them all",
        rationale="the per-controller sum, not just the aggregate, must clear the cap (FR-CAM-005)",
    ),
    MitigationStep(
        order=3,
        action="Disable depth on any RealSense that does not need it",
        rationale="a depth-on RealSense counts as two streams; dropping depth removes one summand",
    ),
    MitigationStep(
        order=4,
        action="Lower the frame rate on one or more cameras",
        rationale="bandwidth scales linearly in fps",
    ),
    MitigationStep(
        order=5,
        action="Lower the resolution on one or more cameras",
        rationale="bandwidth scales in W×H, the largest lever left once fps is reduced",
    ),
)


@dataclass(frozen=True)
class FrameTimeoutCause:
    """One of the two causes a frame timeout is diagnosed against.

    Attributes:
        label: The cause identifier (`bandwidth` or `power`).
        check: What to verify for this cause.
    """

    label: str
    check: str


@dataclass(frozen=True)
class FrameTimeoutDiagnosis:
    """The diagnosis of the RealSense frame-timeout symptom.

    Attributes:
        symptom: The verbatim error the camera stack raises.
        causes: Both independent causes, so neither is silently ruled out.
    """

    symptom: str
    causes: tuple[FrameTimeoutCause, ...]


def mitigation_steps() -> tuple[MitigationStep, ...]:
    """Return the mitigation ladder offered when a configuration is blocked.

    Returns:
        (tuple[MitigationStep, ...]) The five rungs in cheapest-first order.
    """
    return MITIGATION_LADDER


def diagnose_frame_timeout() -> FrameTimeoutDiagnosis:
    """Diagnose `"Frame did not arrive in time"` against both of its causes.

    The symptom is ambiguous by construction: a starved bus and an under-powered
    bus produce the identical message. Returning both causes is the contract
    (`02b` WP-3B-02 ④) — the block layer must never present it as bandwidth-only.

    Returns:
        (FrameTimeoutDiagnosis) The symptom paired with its bandwidth and power causes.
    """
    return FrameTimeoutDiagnosis(
        symptom=FRAME_TIMEOUT_SYMPTOM,
        causes=(
            FrameTimeoutCause(
                label=CAUSE_BANDWIDTH,
                check="the aggregate or a controller sum exceeds the USB3 effective cap",
            ),
            FrameTimeoutCause(
                label=CAUSE_POWER,
                check="the camera draws more than the bus or an unpowered hub can supply",
            ),
        ),
    )


# A construction-time guard: the acceptance criterion counts five rungs, so a future
# edit that adds or drops one and forgets to update the count fails here, not silently.
assert len(MITIGATION_LADDER) == MITIGATION_STEP_COUNT


__all__ = [
    "MITIGATION_LADDER",
    "FrameTimeoutCause",
    "FrameTimeoutDiagnosis",
    "MitigationStep",
    "diagnose_frame_timeout",
    "mitigation_steps",
]
