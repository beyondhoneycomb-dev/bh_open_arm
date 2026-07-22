"""Acceptance ⑨: f_max = min(f_max_can, f_max_python), the x 0.8 ceiling, the 0.95 test.

The arithmetic runs here; the CAN-bound input is deferred, so a missing f_max_can
falls back to the Python bound and records that it is awaited rather than inventing it.
"""

from __future__ import annotations

import pytest

from backend.rtbench.constants import FINAL_GATE
from backend.rtbench.fmax import (
    TargetExceedsFmaxError,
    compute_fmax,
    enforce_target_hz,
    meets_actual_hz,
)


def test_fmax_is_the_minimum_of_both_bounds() -> None:
    fmax = compute_fmax(f_max_can_hz=500.0, f_max_python_hz=400.0)
    assert fmax.f_max_hz == 400.0
    assert fmax.max_target_hz() == pytest.approx(320.0)
    assert fmax.provisional is True  # the Python bound is always synthetic


def test_missing_can_bound_falls_back_and_is_recorded_as_awaited() -> None:
    fmax = compute_fmax(f_max_can_hz=None, f_max_python_hz=400.0)
    assert fmax.f_max_hz == 400.0
    assert fmax.awaiting == ("f_max_can",)
    assert fmax.provisional is True


def test_missing_python_bound_uses_the_can_bound() -> None:
    fmax = compute_fmax(f_max_can_hz=500.0, f_max_python_hz=None)
    assert fmax.f_max_hz == 500.0
    assert fmax.awaiting == ("f_max_python",)


def test_both_bounds_absent_leaves_fmax_unknown() -> None:
    fmax = compute_fmax(f_max_can_hz=None, f_max_python_hz=None)
    assert fmax.f_max_hz is None
    assert fmax.max_target_hz() is None
    assert set(fmax.awaiting) == {"f_max_can", "f_max_python"}
    assert fmax.as_record()["superseded_by"] == FINAL_GATE


def test_enforce_target_hz_rejects_above_the_ceiling() -> None:
    fmax = compute_fmax(f_max_can_hz=500.0, f_max_python_hz=400.0)  # ceiling 320
    enforce_target_hz(320.0, fmax)  # at the ceiling: allowed
    with pytest.raises(TargetExceedsFmaxError):
        enforce_target_hz(320.001, fmax)


def test_enforce_target_hz_does_not_invent_a_ceiling_when_fmax_unknown() -> None:
    fmax = compute_fmax(f_max_can_hz=None, f_max_python_hz=None)
    # No ceiling to enforce; the caller must hold the target on `awaiting`, not treat
    # the unknown ceiling as permission — enforce simply does not raise.
    enforce_target_hz(10_000.0, fmax)


def test_meets_actual_hz_uses_the_0_95_threshold() -> None:
    assert meets_actual_hz(actual_hz=95.0, target_hz=100.0) is True
    assert meets_actual_hz(actual_hz=94.9, target_hz=100.0) is False
