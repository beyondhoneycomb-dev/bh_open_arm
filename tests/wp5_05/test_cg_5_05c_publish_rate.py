"""CG-5-05c — WS publish rate obeys 30 Hz default / 60 Hz cap, no full-rate leak.

The governor mirrors the frontend contract: default 30, cap 60, a request over the cap
rejected (not clamped), a malformed request rejected. The leak invariant is that the
fast control loop's full rate cannot resolve as a publish rate (the cap sits below it)
and the default is a strict decimation of every control loop.
"""

from __future__ import annotations

import math

from backend.loadtest import resolve_publish_rate, verify_publish_rate_policy
from backend.loadtest.constants import CONTROL_LOOP_POLL_RATES_HZ
from backend.loadtest.publish_rate import full_rate_leaks
from backend.ws.constants import WS_PUBLISH_RATE_DEFAULT_HZ, WS_PUBLISH_RATE_MAX_HZ


def test_unset_resolves_to_default() -> None:
    result = resolve_publish_rate(None)
    assert result.ok
    assert result.hz == WS_PUBLISH_RATE_DEFAULT_HZ == 30.0


def test_cap_is_sixty_and_at_cap_is_allowed() -> None:
    assert WS_PUBLISH_RATE_MAX_HZ == 60.0
    at_cap = resolve_publish_rate(WS_PUBLISH_RATE_MAX_HZ)
    assert at_cap.ok and at_cap.hz == 60.0


def test_over_cap_is_rejected_not_clamped() -> None:
    over = resolve_publish_rate(WS_PUBLISH_RATE_MAX_HZ + 0.1)
    assert not over.ok
    assert "cap" in over.reason
    # Rejected, not clamped: it does not silently resolve to 60.
    assert over.hz != WS_PUBLISH_RATE_MAX_HZ


def test_malformed_requests_are_rejected() -> None:
    assert not resolve_publish_rate(0.0).ok
    assert not resolve_publish_rate(-5.0).ok
    assert not resolve_publish_rate(math.inf).ok
    assert not resolve_publish_rate(math.nan).ok


def test_fast_control_loop_full_rate_cannot_resolve() -> None:
    fastest = max(CONTROL_LOOP_POLL_RATES_HZ)
    # The 100 Hz loop's full rate must not resolve as a publish rate (it is over the cap).
    assert not resolve_publish_rate(fastest).ok


def test_default_decimates_every_control_loop() -> None:
    for loop_hz in CONTROL_LOOP_POLL_RATES_HZ:
        assert not full_rate_leaks(WS_PUBLISH_RATE_DEFAULT_HZ, loop_hz)
    # And publishing at (or above) the loop rate IS a leak — the check is not vacuous.
    assert full_rate_leaks(100.0, 100.0)


def test_policy_verdict_holds() -> None:
    verdict = verify_publish_rate_policy()
    assert verdict.holds
    assert verdict.default_hz == 30.0
    assert verdict.cap_hz == 60.0
    assert verdict.over_cap_rejected
    assert verdict.fast_loop_full_rate_rejected
    assert verdict.default_decimates_all_loops
    assert verdict.violations == ()
