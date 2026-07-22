"""Acceptance ③ + negative branch — operator-only clear, and no auto-resume.

③ `clear_error` fires only after an explicit operator confirmation (`12` FR-SAF-028).
Negative branch (`FAIL_BLOCKING`): a fault detected then auto-resumed is a latch
violation. Every cycle after a latch stays held until an operator clears it
(`12` FR-SAF-043); a healthy frame, a quiet bus, or the bus returning must never
resume motion on their own.
"""

from __future__ import annotations

import pytest

from backend.commloss import (
    CLEAR_ERROR_PAYLOAD,
    OperatorConfirmation,
    UnconfirmedClearError,
    WatchdogCause,
)
from contracts.errors.constants import DAMIAO_ENABLE_NIBBLE
from tests.wp2a07.support import build_watchdog, frames, silence, status_byte

# An overvoltage frame (nibble 8) stands in for any decoded fault; a healthy frame
# is the enable state upstream reports on a nominal cycle.
_FAULT = status_byte(0x8)
_HEALTHY = status_byte(DAMIAO_ENABLE_NIBBLE)


def test_clear_error_requires_operator_confirmation() -> None:
    """Without a confirmation the clear is refused and the latch stays engaged (③)."""
    watchdog, latch, _ = build_watchdog()
    watchdog.service(frames(_FAULT))
    assert latch.is_active
    with pytest.raises(UnconfirmedClearError):
        watchdog.clear_error(None)
    assert latch.is_active


def test_confirmed_clear_releases_latch_and_returns_command() -> None:
    """An explicit confirmation clears the latch and yields the Clear-Error payload (③)."""
    watchdog, latch, _ = build_watchdog()
    watchdog.service(frames(_FAULT))
    command = watchdog.clear_error(OperatorConfirmation(operator="op-1"))
    assert command.payload == CLEAR_ERROR_PAYLOAD
    assert not latch.is_active


def test_healthy_frame_after_fault_does_not_resume() -> None:
    """A fault then healthy frames stays held — auto-resume would be FAIL_BLOCKING."""
    watchdog, latch, _ = build_watchdog()
    assert watchdog.service(frames(_FAULT)).newly_latched
    for _ in range(5):
        verdict = watchdog.service(frames(_HEALTHY))
        assert verdict.latched
        assert not verdict.newly_latched
        assert latch.is_active


def test_silence_after_fault_does_not_resume() -> None:
    """The held state survives quiet cycles too — nothing but an operator ack clears it."""
    watchdog, latch, _ = build_watchdog()
    watchdog.service(frames(_FAULT))
    assert watchdog.service(silence()).latched
    assert latch.is_active


def test_comm_loss_then_frames_return_does_not_resume() -> None:
    """A comm loss that then sees frames again stays held — the return is not a resume."""
    watchdog, latch, clock = build_watchdog()
    clock.advance(0.02)
    assert watchdog.service(silence()).cause is WatchdogCause.COMM_LOSS
    verdict = watchdog.service(frames(_HEALTHY))
    assert verdict.latched
    assert not verdict.newly_latched
    assert latch.is_active


def test_confirmed_clear_is_a_real_reset_not_a_permanent_disable() -> None:
    """A confirmed clear resumes normal watch: a later fault re-latches anew."""
    watchdog, latch, _ = build_watchdog()
    watchdog.service(frames(_FAULT))
    watchdog.clear_error(OperatorConfirmation(operator="op-1"))
    assert not latch.is_active
    # A healthy frame after the clear runs clean, and a new fault re-latches.
    assert not watchdog.service(frames(_HEALTHY)).latched
    assert watchdog.service(frames(_FAULT)).newly_latched
    assert latch.is_active
