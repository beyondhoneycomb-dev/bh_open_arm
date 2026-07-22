"""Acceptance ⑤/⑥(offline part)/⑨: the explicit set-zero flow.

The residual-within-±0.5° assertion of ⑥ needs a real motor readback and is deferred;
the residual ARITHMETIC and the refusal branches run here against a fixture bus.
"""

from __future__ import annotations

import pytest

from backend.calibration.schema import MOTOR_ORDER, CalibrationError, ZeroMethod


def test_set_zero_refused_while_torque_enabled(make_follower) -> None:
    """set_zero refuses on an enabled motor rather than let 0xFE be silently skipped (⑤)."""
    follower, bus = make_follower()
    follower.connect_readonly()
    follower._torque_enabled = True  # simulate an enabled arm entering the flow
    with pytest.raises(CalibrationError) as refused:
        follower.set_zero(ZeroMethod.HARDSTOP_BUMP, rest_confirmed=True)
    assert "torque" in str(refused.value).lower()
    # No 0xFE was emitted on the refused attempt.
    assert "set_zero_position" not in bus.commands


def test_set_zero_disables_before_emitting_0xfe(make_follower) -> None:
    """The flow disables all motors before the single 0xFE (disable-first, FR-CON-063)."""
    follower, bus = make_follower()
    follower.connect_readonly()
    follower.set_zero(ZeroMethod.HARDSTOP_BUMP, rest_confirmed=True)
    disable_at = bus.commands.index("disable_torque")
    zero_at = bus.commands.index("set_zero_position")
    assert disable_at < zero_at, "disable_torque must precede set_zero_position"


def test_set_zero_emits_exactly_one_0xfe(make_follower) -> None:
    """Running the flow once emits exactly one 0xFE set-zero command."""
    follower, bus = make_follower()
    follower.connect_readonly()
    follower.set_zero(ZeroMethod.HARDSTOP_BUMP, rest_confirmed=True)
    assert bus.commands.count("set_zero_position") == 1


def test_set_zero_records_zero_method_and_residual(make_follower) -> None:
    """A successful set-zero persists the zero_method and the measured residual (⑨)."""
    follower, _bus = make_follower(position_deg=0.0)
    follower.connect_readonly()
    result = follower.set_zero(ZeroMethod.MECHANICAL_JIG, rest_confirmed=True)
    assert result.within_tolerance
    calibration = follower.calibration_model
    assert calibration is not None
    assert calibration.zero_method is ZeroMethod.MECHANICAL_JIG
    assert calibration.zero_residual_deg == [0.0] * len(MOTOR_ORDER)
    assert calibration.last_zero_at is not None


def test_set_zero_refused_when_residual_exceeds_tolerance(make_follower) -> None:
    """A readback outside ±0.5° of the URDF-zero reference forces a re-zero (⑥ arithmetic).

    After 0xFE the motor reads ~0°, but the arm was aligned 5° off the URDF-zero rest
    pose (urdf_zero_offset=5°), so the residual is 5° — past the ±0.5° tolerance.
    """
    follower, _bus = make_follower(position_deg=0.0)
    follower.connect_readonly()
    with pytest.raises(CalibrationError) as exceeded:
        follower.set_zero(
            ZeroMethod.HARDSTOP_BUMP,
            rest_confirmed=True,
            urdf_zero_offset_deg=[5.0] * len(MOTOR_ORDER),
        )
    assert "residual" in str(exceeded.value).lower()
    # The bad zero was not persisted.
    assert follower.is_calibrated is False
    assert follower.calibration_model is None
