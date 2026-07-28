"""The banners the detection activation gate shows for each non-active mode (FR-SAF-029/030/001b).

Three states carry a banner and one does not: DISABLED shows the always-on detection-disabled
notice, DEGRADED shows the effective-detection-delay and the lowered speed cap, ARCHITECTURE_REOPEN
shows the observer-divergence escalation, and a fully ACTIVE loop shows nothing. Only the disabled
text is fixed copy; the other two are formatters, because a banner an operator cannot act on is
the alibi 02b §3.3 forbids — the degrade must show the measured latency and the enforced cap, and
the escalation must show which gain, period and bound produced it.

This is a different banner from WP-2B-08's `PathBBanner`: that one is scoped to the path-B fallback
session (friction identification failed → gravity+Coriolis bootstrap, friction uncompensated),
while this is the general FR-SAF-030 detection-disabled banner for any non-PASS PG-FRIC-001 verdict,
of which path-B's permanent FAIL_BLOCKING is one input.
"""

from __future__ import annotations

from backend.detection_gate.constants import (
    DEGRADED_BANNER_TEMPLATE,
    DISABLED_BANNER_DETAIL,
    DISABLED_BANNER_HEADLINE,
    FORWARD_EULER_STABILITY_BOUND,
    REOPEN_BANNER_DETAIL_TEMPLATE,
    REOPEN_BANNER_HEADLINE,
)
from backend.detection_gate.convergence import converging_rate_floor_hz

# The degraded banner renders the effective delay in milliseconds and the speed cap as a percent;
# both factors convert the gate's SI-second latency and unit-fraction cap into the display units.
MILLISECONDS_PER_SECOND = 1000.0
PERCENT_PER_UNIT = 100.0


def disabled_banner_text() -> str:
    """The always-shown detection-disabled banner (FR-SAF-029/030, 02b §3.0).

    Returns:
        (str) Headline and detail joined for a one-line render.
    """
    return f"{DISABLED_BANNER_HEADLINE} — {DISABLED_BANNER_DETAIL}"


def reopen_banner_text(observer_gain: float, detection_dt_s: float) -> str:
    """The architecture-reopen banner (02b §3.2 negative branch, NORM-008).

    The escalation asks the operator to change something, so it names what: the gain in force, the
    period the loop actually achieved, their product against the bound, and the rate that gain
    would need. Without those the banner says only that detection is off.

    Args:
        observer_gain: The residual-loop gain `K` the verdict was resolved against.
        detection_dt_s: The measured loop period, s (the band's effective latency).

    Returns:
        (str) Headline and filled detail joined for a one-line render.
    """
    detail = REOPEN_BANNER_DETAIL_TEMPLATE.format(
        bound=FORWARD_EULER_STABILITY_BOUND,
        observer_gain=observer_gain,
        period_ms=detection_dt_s * MILLISECONDS_PER_SECOND,
        gain_period_product=observer_gain * detection_dt_s,
        floor_hz=converging_rate_floor_hz(observer_gain),
    )
    return f"{REOPEN_BANNER_HEADLINE} — {detail}"


def degraded_banner_text(effective_latency_sec: float, speed_cap_scale: float) -> str:
    """The degraded banner, carrying the effective delay and the enforced speed cap (③).

    Both numbers are load-bearing: the effective latency is the ≈1/f detection delay FR-SAF-001b
    requires shown, and the speed-cap percent is the jog/teleop downgrade the state actually
    enforces. Rendering the latency without the cap is the alibi 02b §3.3 forbids, so the
    formatter takes both and neither is optional.

    Args:
        effective_latency_sec: The effective detection delay in seconds (≈1/effective_hz).
        speed_cap_scale: The jog/teleop speed-cap fraction the downgrade enforces (< 1.0).

    Returns:
        (str) The degraded banner with the delay in milliseconds and the cap as a percent.
    """
    return DEGRADED_BANNER_TEMPLATE.format(
        latency_ms=effective_latency_sec * MILLISECONDS_PER_SECOND,
        cap_percent=speed_cap_scale * PERCENT_PER_UNIT,
    )
