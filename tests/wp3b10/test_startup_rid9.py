"""Startup loop-period vs RID9 check (`FR-TEL-080`, `PG-RID-001`).

The teleop loop period must be strictly shorter than the Damiao RID9 comm-loss
timeout, or every frame risks the motor enable dropping (and the arm falling). The
check verifies this at startup; RID9 = 0 is the "HW fallback disabled" flag, not a
period, and any timeout the loop cannot beat blocks torque-on.
"""

from __future__ import annotations

import pytest

from backend.teleop.safety_gate.startup import (
    LoopPeriodError,
    Rid9Verdict,
    evaluate_loop_period,
    verify_loop_period_under_rid9_timeout,
)

_LOOP_60HZ = 1.0 / 60.0  # 16.7 ms


def test_loop_faster_than_timeout_permits_torque_on() -> None:
    """A loop period below the RID9 timeout is OK and permits torque-on."""
    result = evaluate_loop_period(_LOOP_60HZ, rid9_timeout_sec=0.05)
    assert result.verdict is Rid9Verdict.OK
    assert result.permits_torque_on is True


def test_loop_not_faster_than_timeout_blocks_torque_on() -> None:
    """A loop period at or above the RID9 timeout blocks torque-on (FR-TEL-080)."""
    result = evaluate_loop_period(0.05, rid9_timeout_sec=_LOOP_60HZ)
    assert result.verdict is Rid9Verdict.TORQUE_ON_BLOCKED
    assert result.permits_torque_on is False


def test_equal_period_and_timeout_blocks_torque_on() -> None:
    """The period must be *strictly* shorter; equality is blocked."""
    result = evaluate_loop_period(0.05, rid9_timeout_sec=0.05)
    assert result.verdict is Rid9Verdict.TORQUE_ON_BLOCKED


def test_rid9_zero_is_the_hw_fallback_disabled_flag() -> None:
    """RID9 = 0 reports the disabled HW comm-loss fallback, not a timing verdict (PG-RID-001)."""
    result = evaluate_loop_period(_LOOP_60HZ, rid9_timeout_sec=0.0)
    assert result.verdict is Rid9Verdict.HW_FALLBACK_DISABLED
    assert result.permits_torque_on is True


def test_verify_raises_when_torque_on_blocked() -> None:
    """The gating form raises rather than returning when the loop cannot beat the timeout."""
    with pytest.raises(LoopPeriodError, match="torque-on is blocked"):
        verify_loop_period_under_rid9_timeout(0.05, rid9_timeout_sec=_LOOP_60HZ)


def test_verify_returns_result_when_permitted() -> None:
    """The gating form returns the result when torque-on is permitted."""
    result = verify_loop_period_under_rid9_timeout(_LOOP_60HZ, rid9_timeout_sec=0.05)
    assert result.permits_torque_on is True


def test_bad_inputs_are_rejected() -> None:
    """A non-positive loop period or negative timeout is rejected."""
    with pytest.raises(ValueError, match="loop period must be positive"):
        evaluate_loop_period(0.0, rid9_timeout_sec=0.05)
    with pytest.raises(ValueError, match="cannot be negative"):
        evaluate_loop_period(_LOOP_60HZ, rid9_timeout_sec=-0.01)
