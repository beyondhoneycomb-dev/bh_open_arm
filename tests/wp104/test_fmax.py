"""Acceptance ⑨: f_max = min(f_max_can, f_max_python) and the x 0.8 figure it derives.

The arithmetic runs here; the CAN-bound input is deferred, so a missing f_max_can
falls back to the Python bound and records that it is awaited rather than inventing it.
Under NORM-008 the x 0.8 figure is published and not enforced, so what is pinned is that
it is still computed and that the record renders no pass line from it.
"""

from __future__ import annotations

import pytest

from backend.rtbench.constants import FINAL_GATE
from backend.rtbench.fmax import compute_fmax


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


def test_fmax_record_publishes_no_pass_line() -> None:
    # NORM-008: the ceiling is published as a figure to read, so the record must state
    # that it renders no verdict and must not ship an on-time pass ratio alongside it.
    record = compute_fmax(f_max_can_hz=500.0, f_max_python_hz=400.0).as_record()
    assert "actual_hz_pass_ratio" not in record
    assert record["is_verdict"] is False
    assert record["max_target_hz"] == pytest.approx(320.0)
