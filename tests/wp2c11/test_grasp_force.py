"""Grasp force is classified by the absolute value of gripper.torque, per-unit only.

FR-SAF-024b: the threshold is on |gripper.torque|, so sign is a direction; a reading at
or above the force cap raises the over-grip alarm. The thresholds are validated to the
per-unit domain [0, 1] at construction (a physical value is refused), while a live
reading is never refused — a hot magnitude still grades as an alarm.
"""

from __future__ import annotations

import pytest

from backend.temp_gripper.errors import TempGripperConfigError
from backend.temp_gripper.grasp import GraspForceMonitor, GraspState

_CONTACT_PU = 0.05
_CAP_PU = 0.8


def _monitor() -> GraspForceMonitor:
    return GraspForceMonitor(contact_threshold_pu=_CONTACT_PU, force_cap_pu=_CAP_PU)


def test_below_contact_is_released() -> None:
    verdict = _monitor().classify(0.01)
    assert verdict.state is GraspState.RELEASED
    assert not verdict.over_grip


def test_between_contact_and_cap_is_grasping() -> None:
    verdict = _monitor().classify(0.4)
    assert verdict.state is GraspState.GRASPING
    assert not verdict.over_grip


def test_at_or_above_cap_is_over_grip_alarm() -> None:
    at_cap = _monitor().classify(_CAP_PU)
    above = _monitor().classify(0.95)
    assert at_cap.state is GraspState.OVER_GRIP and at_cap.over_grip
    assert above.state is GraspState.OVER_GRIP and above.over_grip


def test_threshold_is_on_absolute_value() -> None:
    # A negative torque of the same magnitude classifies identically — sign is direction.
    negative = _monitor().classify(-0.9)
    assert negative.state is GraspState.OVER_GRIP
    assert negative.torque_pu_abs == 0.9


def test_live_out_of_domain_reading_still_alarms_not_raises() -> None:
    # A live magnitude above 1.0 is a mis-scaled input; it must alarm, never crash.
    verdict = _monitor().classify(1.5)
    assert verdict.state is GraspState.OVER_GRIP


def test_config_threshold_outside_per_unit_is_refused() -> None:
    with pytest.raises(TempGripperConfigError, match="per-unit"):
        GraspForceMonitor(contact_threshold_pu=0.05, force_cap_pu=5.0)


def test_config_contact_not_below_cap_is_refused() -> None:
    with pytest.raises(TempGripperConfigError, match="must be below the force cap"):
        GraspForceMonitor(contact_threshold_pu=0.8, force_cap_pu=0.5)


def test_default_monitor_constructs() -> None:
    # The default per-unit thresholds are a valid config.
    verdict = GraspForceMonitor().classify(0.4)
    assert verdict.state is GraspState.GRASPING
