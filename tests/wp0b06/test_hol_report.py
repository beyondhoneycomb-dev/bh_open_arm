"""HOL report — the structural single-WebSocket head-of-line characterisation.

Runs here (pure structural report). The measured delay distribution is the deferred
part; this pins that the structural verdict is always stated and that an unmeasured
delay is rendered as absent, never as a fabricated zero.
"""

from __future__ import annotations

from ops.hw.usb.hol import build_hol_report


def test_hol_is_structurally_inevitable_with_stated_causes() -> None:
    """The report always states HOL as inevitable, with both structural causes."""
    report = build_hol_report()
    assert report.hol_inevitable is True
    assert len(report.causes) == 2
    assert any("RFC 6455" in cause for cause in report.causes)
    assert any("backpressure" in cause for cause in report.causes)


def test_unmeasured_delay_is_absent_not_zero() -> None:
    """With no traffic measured, the delay distribution is None (honestly unmeasured)."""
    report = build_hol_report()
    assert report.delay_distribution is None
    assert report.as_dict()["delay_distribution"] is None


def test_measured_delay_attaches_distribution() -> None:
    """Supplied head-of-line delays produce a real distribution with a histogram."""
    report = build_hol_report([1000.0, 5000.0, 12000.0, 800.0])
    assert report.delay_distribution is not None
    assert report.delay_distribution.histogram
    payload = report.as_dict()["delay_distribution"]
    assert isinstance(payload, dict)
    assert payload["count"] == 4
