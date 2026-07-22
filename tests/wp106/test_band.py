"""Acceptance ⑪: the detection-loop bandwidth verdict over WP-1-04's provisional f_max.

Pattern A admits the 1 kHz target; pattern B clamps to the 625 Hz CAN-FD ceiling with a
degraded flag and an effective-latency display. The verdict stays provisional because the
f_max_python it consumes is provisional and named PG-RT-001b as its supersede trigger.
"""

from __future__ import annotations

import pytest

from backend.rtbench.fmax import compute_fmax
from backend.safety_bringup import STALE_ON, FramePattern, resolve_detection_band
from backend.safety_bringup.constants import (
    DETECTION_LOOP_PATTERN_B_CEILING_HZ,
    DETECTION_LOOP_TARGET_HZ,
)


def test_stale_trigger_names_pg_rt_001b() -> None:
    # The band rests on a provisional figure and declares its re-derivation trigger.
    assert STALE_ON == "PG-RT-001b:PASS"


def test_pattern_a_admits_one_kilohertz() -> None:
    # ⑪: pattern A with ample f_max keeps the 1 kHz target and is not degraded.
    fmax = compute_fmax(f_max_can_hz=1250.0, f_max_python_hz=2000.0)
    band = resolve_detection_band(FramePattern.A, fmax)
    assert band.effective_hz == DETECTION_LOOP_TARGET_HZ
    assert not band.clamped
    assert not band.degraded
    assert band.provisional


def test_pattern_b_clamps_to_ceiling_and_degrades() -> None:
    # ⑪: pattern B clamps to 625 Hz, flags degraded, and reports an effective latency.
    fmax = compute_fmax(f_max_can_hz=625.0, f_max_python_hz=2000.0)
    band = resolve_detection_band(FramePattern.B, fmax)
    assert band.effective_hz == DETECTION_LOOP_PATTERN_B_CEILING_HZ
    assert band.clamped
    assert band.degraded
    assert band.effective_latency_sec == pytest.approx(1.0 / DETECTION_LOOP_PATTERN_B_CEILING_HZ)


def test_fmax_python_bounds_the_band_below_the_ceiling() -> None:
    # A provisional f_max_python below the ceiling bounds the effective rate further.
    fmax = compute_fmax(f_max_can_hz=None, f_max_python_hz=400.0)
    band = resolve_detection_band(FramePattern.B, fmax)
    assert band.effective_hz == pytest.approx(400.0)
    assert band.degraded
    assert band.provisional
