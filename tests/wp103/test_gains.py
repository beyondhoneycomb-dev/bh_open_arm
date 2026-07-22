"""Acceptance ⑦ — kp/kd validated then rejected, never silently wrapped (`03` FR-MOT-018).

The CAN packet carries kp in a 12-bit field scaled to [0,500] and kd to [0,5]; an
over-range gain is silently wrapped by the encoder into a different, unrequested
stiffness that would run anyway. So a gain outside its range is rejected at the
gateway before it can reach the wire, with its own distinct reason.
"""

from __future__ import annotations

from backend.actuation import SafetyReason
from tests.wp103.conftest import degs, make_gateway, make_limits


def test_kp_above_500_is_rejected() -> None:
    """A stiffness above 500 is rejected, not wrapped (⑦)."""
    gateway, _guard = make_gateway(make_limits())
    result = gateway.submit(degs(1.0, 1.0), degs(0.0, 0.0), kp=(600.0, 100.0))
    assert result.rejected
    assert result.reason is SafetyReason.KP_OUT_OF_RANGE


def test_kd_above_5_is_rejected() -> None:
    """A damping above 5 is rejected, not wrapped (⑦)."""
    gateway, _guard = make_gateway(make_limits())
    result = gateway.submit(degs(1.0, 1.0), degs(0.0, 0.0), kd=(6.0, 1.0))
    assert result.rejected
    assert result.reason is SafetyReason.KD_OUT_OF_RANGE


def test_in_range_gains_are_accepted() -> None:
    """Gains inside their ranges pass the gain check (⑦, no over-eager reject)."""
    gateway, _guard = make_gateway(make_limits())
    result = gateway.submit(degs(1.0, 1.0), degs(0.0, 0.0), kp=(240.0, 240.0), kd=(5.0, 3.0))
    assert not result.rejected
    assert result.reason is SafetyReason.NONE


def test_boundary_gains_are_accepted() -> None:
    """The inclusive bounds (0 and the max) are in range (⑦)."""
    gateway, _guard = make_gateway(make_limits())
    result = gateway.submit(degs(1.0, 1.0), degs(0.0, 0.0), kp=(0.0, 500.0), kd=(0.0, 5.0))
    assert not result.rejected
