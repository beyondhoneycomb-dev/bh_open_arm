"""The WS publish-rate governor and its no-full-rate-leak check (`CG-5-05c`).

`NFR-GUI-003` fixes the joint-state WS publish rate at 30 Hz default, 60 Hz cap, and
forbids pushing the control-loop full rate straight onto the WS. This module is the
Python mirror of the frontend `resolvePublishRate` governor, plus the leak check the
load test needs: the cap sits strictly below the
fast control loop (100 Hz), so the fast loop's full rate can never resolve as a publish
rate, and a request AT that rate is rejected rather than clamped.

A request over the cap is rejected, not clamped, for the same reason the frontend
rejects it: silently clamping hides that the operator asked for a rate the platform
will not sustain.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from backend.loadtest.constants import CONTROL_LOOP_POLL_RATES_HZ
from backend.ws.constants import WS_PUBLISH_RATE_DEFAULT_HZ, WS_PUBLISH_RATE_MAX_HZ


@dataclass(frozen=True)
class PublishRateResolution:
    """The outcome of resolving a requested publish rate.

    Attributes:
        ok: Whether the request resolved to an allowed rate.
        hz: The resolved rate when `ok`; the requested value otherwise.
        reason: Why a request was refused; empty when `ok`.
    """

    ok: bool
    hz: float
    reason: str


def resolve_publish_rate(requested_hz: float | None) -> PublishRateResolution:
    """Resolve a requested joint-state publish rate against the 30/60 Hz contract.

    An unset request resolves to the 30 Hz default; a non-positive or non-finite
    request is malformed; a request over the 60 Hz cap is refused (not clamped).

    Args:
        requested_hz: The operator's requested rate, or None for the default.

    Returns:
        (PublishRateResolution) The resolved rate, or a refusal with its reason.
    """
    if requested_hz is None:
        return PublishRateResolution(ok=True, hz=WS_PUBLISH_RATE_DEFAULT_HZ, reason="")
    if not math.isfinite(requested_hz) or requested_hz <= 0.0:
        return PublishRateResolution(
            ok=False, hz=requested_hz, reason="publish rate must be a positive, finite number"
        )
    if requested_hz > WS_PUBLISH_RATE_MAX_HZ:
        return PublishRateResolution(
            ok=False,
            hz=requested_hz,
            reason=f"publish rate {requested_hz} Hz exceeds the {WS_PUBLISH_RATE_MAX_HZ} Hz cap",
        )
    return PublishRateResolution(ok=True, hz=requested_hz, reason="")


def full_rate_leaks(published_hz: float, control_loop_hz: float) -> bool:
    """Whether a publish rate would forward the control loop's full rate (a leak).

    A leak is the WS carrying the control loop at (or above) its own poll rate rather
    than a decimation of it. Publishing below the loop rate is a genuine decimation;
    publishing at or above it means every control tick reaches the wire.

    Args:
        published_hz: The resolved WS publish rate.
        control_loop_hz: The control-loop poll rate.

    Returns:
        (bool) True when `published_hz` is not a decimation of `control_loop_hz`.
    """
    return published_hz >= control_loop_hz


@dataclass(frozen=True)
class PublishRateVerdict:
    """The `CG-5-05c` verdict: the 30/60 contract holds and no full rate leaks.

    Attributes:
        default_hz: The resolved default publish rate (must be 30).
        cap_hz: The cap (must be 60).
        over_cap_rejected: A request one hertz over the cap is refused.
        fast_loop_full_rate_rejected: A request at the fastest control-loop rate is
            refused by the cap — the fast loop's full rate can never resolve.
        default_decimates_all_loops: The default rate is strictly below every
            control-loop poll rate, so it is a real decimation of each.
        violations: One line per rule that did not hold; empty when the contract holds.
    """

    default_hz: float
    cap_hz: float
    over_cap_rejected: bool
    fast_loop_full_rate_rejected: bool
    default_decimates_all_loops: bool
    violations: tuple[str, ...]

    @property
    def holds(self) -> bool:
        """Whether the publish-rate contract held with no full-rate leak."""
        return not self.violations


def verify_publish_rate_policy() -> PublishRateVerdict:
    """Verify the 30/60 publish-rate contract and the no-full-rate-leak invariant.

    Returns:
        (PublishRateVerdict) The result of resolving the default, an over-cap request,
        and each control-loop full rate, plus the decimation check.
    """
    violations: list[str] = []

    default = resolve_publish_rate(None)
    if not (default.ok and default.hz == WS_PUBLISH_RATE_DEFAULT_HZ):
        violations.append(f"default did not resolve to {WS_PUBLISH_RATE_DEFAULT_HZ} Hz")

    over_cap = resolve_publish_rate(WS_PUBLISH_RATE_MAX_HZ + 1.0)
    if over_cap.ok:
        violations.append("a request above the 60 Hz cap was not rejected")

    fastest_loop = max(CONTROL_LOOP_POLL_RATES_HZ)
    fast_loop_rejected = not resolve_publish_rate(fastest_loop).ok
    if not fast_loop_rejected:
        violations.append(
            f"the fastest control loop ({fastest_loop} Hz) resolves as a publish rate — "
            "the control-loop full rate can leak onto the WS"
        )

    default_decimates = all(
        not full_rate_leaks(WS_PUBLISH_RATE_DEFAULT_HZ, loop_hz)
        for loop_hz in CONTROL_LOOP_POLL_RATES_HZ
    )
    if not default_decimates:
        violations.append("the default publish rate is not a decimation of every control loop")

    return PublishRateVerdict(
        default_hz=default.hz,
        cap_hz=WS_PUBLISH_RATE_MAX_HZ,
        over_cap_rejected=not over_cap.ok,
        fast_loop_full_rate_rejected=fast_loop_rejected,
        default_decimates_all_loops=default_decimates,
        violations=tuple(violations),
    )
