"""Acceptance ④ — `recv_all()` silence beyond the timeout triggers a safe stop.

`04` FR-MAN-056 / `12` FR-SAF-027: a receive that returns nothing for
`comm_timeout_ms` (default 10 ms) is a comm loss, and the watchdog latches a safe
stop. This is a distinct detection from the ERR decode — the timer fires precisely
when NO frame arrives, which the decoder, needing a frame, can never see.
"""

from __future__ import annotations

from backend.commloss import DEFAULT_COMM_TIMEOUT_SEC, WatchdogCause
from contracts.errors.constants import DAMIAO_ENABLE_NIBBLE
from tests.wp2a07.support import build_watchdog, frames, silence, status_byte


def test_silence_beyond_timeout_latches_safe_stop() -> None:
    """Silence past the timeout latches a comm-loss safe stop immediately (④)."""
    watchdog, latch, clock = build_watchdog()
    clock.advance(DEFAULT_COMM_TIMEOUT_SEC + 0.001)
    verdict = watchdog.service(silence())
    assert verdict.latched
    assert verdict.newly_latched
    assert verdict.cause is WatchdogCause.COMM_LOSS
    assert latch.is_active


def test_silence_within_timeout_does_not_latch() -> None:
    """Silence shorter than the timeout is not yet a comm loss (④, no over-eager stop)."""
    watchdog, latch, clock = build_watchdog()
    clock.advance(DEFAULT_COMM_TIMEOUT_SEC / 2.0)
    verdict = watchdog.service(silence())
    assert not verdict.latched
    assert not latch.is_active


def test_silence_at_exactly_the_timeout_latches() -> None:
    """A gap of exactly the timeout latches — FR-MAN-056 is 'comm_timeout 이상' (>=)."""
    watchdog, latch, clock = build_watchdog()
    clock.advance(DEFAULT_COMM_TIMEOUT_SEC)
    assert watchdog.service(silence()).latched
    assert latch.is_active


def test_a_received_frame_resets_the_silence_timer() -> None:
    """Each received frame restarts the silence window, so a live bus never latches (④)."""
    watchdog, latch, clock = build_watchdog()
    near = DEFAULT_COMM_TIMEOUT_SEC * 0.8
    clock.advance(near)
    assert not watchdog.service(frames(status_byte(DAMIAO_ENABLE_NIBBLE))).latched
    # Another sub-timeout gap after the frame: total elapsed since arming now exceeds
    # the timeout, but measured from the last frame it does not, so no comm loss.
    clock.advance(near)
    assert not watchdog.service(silence()).latched
    assert not latch.is_active
