"""Acceptance ⑥ — the real-fixture re-verification hook (plan 02a §4.1).

The claim that the parsers read *real* kernel/iproute2 output correctly needs a real
capture, which no hardware here can produce, so `test_real_hardware_reverify` skips
with a reason until ``OPENARM_INTRUDER_REAL_FIXTURE`` points at one.

The hook mechanism itself is not deferred: `test_hook_reruns_checks_over_a_capture`
drives `reverify_from_fixture` over a capture directory written here in the real file
layout, proving the hook re-runs the identical WARN/FAULT checks rather than being a
stub. The machinery is exercised; only the real bytes are pending.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.can.intruder.reverify import (
    fixture_dir_from_env,
    reverify_from_fixture,
)
from tests.wp0b03.synth import make_ip_stats, make_rcvlist_all


def _write_capture(
    fixture_dir: Path,
    *,
    listeners: int,
    tx_packets: int,
    expected_own: int,
    baseline_tx: int,
    backend_sent: int,
    expect_warning: bool,
    expect_fault: bool,
) -> None:
    """Write a capture directory in the exact real-fixture file layout."""
    fixture_dir.mkdir(parents=True, exist_ok=True)
    (fixture_dir / "rcvlist_all.txt").write_text(
        make_rcvlist_all({"vcan0": listeners}), encoding="utf-8"
    )
    (fixture_dir / "ip_s_link.txt").write_text(make_ip_stats("vcan0", tx_packets), encoding="utf-8")
    (fixture_dir / "expected.json").write_text(
        json.dumps(
            {
                "iface": "vcan0",
                "expected_own_listeners": expected_own,
                "baseline_tx": baseline_tx,
                "backend_sent_frames": backend_sent,
                "expect_listener_warning": expect_warning,
                "expect_tx_fault": expect_fault,
            }
        ),
        encoding="utf-8",
    )


def test_hook_reruns_checks_over_a_capture(tmp_path: Path) -> None:
    """The hook re-runs the WARN/FAULT checks over a real-layout capture and matches."""
    _write_capture(
        tmp_path,
        listeners=2,
        tx_packets=515,
        expected_own=2,
        baseline_tx=500,
        backend_sent=10,
        expect_warning=False,
        expect_fault=True,
    )
    result = reverify_from_fixture(tmp_path)
    assert result.matched, result.detail
    assert result.warning is None
    assert result.fault is not None


def test_hook_reports_a_verdict_mismatch(tmp_path: Path) -> None:
    """A capture whose recorded expectation disagrees is reported, not passed."""
    _write_capture(
        tmp_path,
        listeners=2,
        tx_packets=510,
        expected_own=2,
        baseline_tx=500,
        backend_sent=10,
        expect_warning=False,
        # The bytes are clean, but the expectation wrongly claims a fault.
        expect_fault=True,
    )
    result = reverify_from_fixture(tmp_path)
    assert not result.matched
    assert "tx fault" in result.detail


@pytest.mark.skipif(
    fixture_dir_from_env() is None,
    reason=(
        "deferred: needs a real hardware/vcan capture; set OPENARM_INTRUDER_REAL_FIXTURE "
        "to a directory holding rcvlist_all.txt + ip_s_link.txt + expected.json"
    ),
)
def test_real_hardware_reverify() -> None:
    """Re-verify against a real capture the moment one is supplied."""
    fixture_dir = fixture_dir_from_env()
    assert fixture_dir is not None
    result = reverify_from_fixture(fixture_dir)
    assert result.matched, result.detail
