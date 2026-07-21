"""Acceptance ④ — per-arm f_max_can by the 0.95 rule + ip -s -d bus statistics.

Runs on synthetic sweep data and a fixture `ip -s -d link show` dump. It pins the
`f_max_can = highest target meeting actual >= 0.95 * target` rule and confirms the
bus-statistics parser extracts the error counters and restarts the acceptance
requires recorded alongside the sweep.
"""

from __future__ import annotations

from pathlib import Path

from ops.hw.usb.fmax import ACHIEVED_FRACTION_THRESHOLD, compute_fmax
from ops.hw.usb.iplink import parse_bus_stats

_FIXTURES = Path(__file__).parent / "fixtures"


def test_fmax_is_highest_target_meeting_threshold() -> None:
    """f_max_can is the top swept target still achieving >= 0.95 of target."""
    # 500 Hz achieves 499 (met); 600 achieves 540 (met = 0.90*600? no): pick clear values.
    sweep = {
        100: 100.0,
        300: 299.0,
        500: 498.0,
        600: 590.0,  # 590 >= 0.95*600 = 570 -> met
        700: 630.0,  # 630 <  0.95*700 = 665 -> missed
        800: 600.0,  # missed
    }
    result = compute_fmax("oa_fl", sweep)
    assert result.f_max_hz == 600
    assert result.iface == "oa_fl"


def test_fmax_none_when_lowest_target_fails() -> None:
    """If even the lowest target misses the bar, f_max is None, not a guess."""
    result = compute_fmax("oa_fr", {100: 50.0, 200: 90.0})
    assert result.f_max_hz is None


def test_fmax_threshold_boundary_is_inclusive() -> None:
    """Exactly 0.95 * target counts as met (the tool's `>=`)."""
    target = 400
    result = compute_fmax("oa_ll", {target: ACHIEVED_FRACTION_THRESHOLD * target})
    assert result.f_max_hz == target


def test_bus_stats_extract_error_counters_and_restarts() -> None:
    """The ip -s -d parser records restarts, bus-errors, and RX/TX frame counts."""
    text = (_FIXTURES / "ip_s_d_can0.txt").read_text(encoding="utf-8")
    stats = parse_bus_stats("can0", text)

    assert stats.state == "ERROR-ACTIVE"
    assert stats.restart_ms == 100
    assert stats.restarts == 2
    assert stats.bus_errors == 14
    assert stats.error_warn == 1
    assert stats.bus_off == 0
    assert stats.rx_packets == 98765
    assert stats.tx_packets == 87654


def test_bus_stats_serialise_for_artifact() -> None:
    """The bus-stats projection carries the error counters as plain data."""
    text = (_FIXTURES / "ip_s_d_can0.txt").read_text(encoding="utf-8")
    payload = parse_bus_stats("can0", text).as_dict()
    assert payload["restarts"] == 2
    assert payload["berr_counter"] == {"tx": 0, "rx": 0}
