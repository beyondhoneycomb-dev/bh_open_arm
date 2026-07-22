"""Acceptance ③ — the temperature fault threshold is capped at driver 115 °C / coil 95 °C.

FR-SAF-026: the fault caps sit below the motor's own self-protection (driver 120 °C,
coil ≤100 °C) so a fault holds the arm before the motor drops its own enable. A fault
configured above its cap is refused, not clamped — a config must never move the hold
past the self-disable point.
"""

from __future__ import annotations

import pytest

from backend.temp_gripper.constants import COIL_TEMP_FAULT_CAP_C, DRIVE_TEMP_FAULT_CAP_C
from backend.temp_gripper.errors import TempGripperConfigError
from backend.temp_gripper.feedback import MotorThermal
from backend.temp_gripper.temperature import (
    TemperatureMonitor,
    TemperatureThresholds,
    TempSeverity,
    default_thresholds,
)


def test_fault_caps_are_driver_115_and_coil_95() -> None:
    assert DRIVE_TEMP_FAULT_CAP_C == 115.0
    assert COIL_TEMP_FAULT_CAP_C == 95.0


def test_default_thresholds_fault_at_the_caps() -> None:
    thresholds = default_thresholds()
    assert thresholds.drive_fault_c == DRIVE_TEMP_FAULT_CAP_C
    assert thresholds.coil_fault_c == COIL_TEMP_FAULT_CAP_C


def test_driver_fault_above_cap_is_refused() -> None:
    with pytest.raises(TempGripperConfigError, match="exceeds the FR-SAF-026 cap"):
        TemperatureThresholds(
            drive_warn_c=100.0, drive_fault_c=120.0, coil_warn_c=80.0, coil_fault_c=95.0
        )


def test_coil_fault_above_cap_is_refused() -> None:
    with pytest.raises(TempGripperConfigError, match="exceeds the FR-SAF-026 cap"):
        TemperatureThresholds(
            drive_warn_c=100.0, drive_fault_c=115.0, coil_warn_c=80.0, coil_fault_c=100.0
        )


def test_warn_at_or_above_fault_is_refused() -> None:
    with pytest.raises(TempGripperConfigError, match="must be below fault"):
        TemperatureThresholds(
            drive_warn_c=115.0, drive_fault_c=115.0, coil_warn_c=80.0, coil_fault_c=95.0
        )


def test_a_fault_at_or_below_cap_is_accepted() -> None:
    # A stricter (lower) fault than the cap is fine; the cap is a ceiling, not a target.
    thresholds = TemperatureThresholds(
        drive_warn_c=90.0, drive_fault_c=110.0, coil_warn_c=70.0, coil_fault_c=90.0
    )
    assert thresholds.drive_fault_c == 110.0


def test_driver_over_cap_reading_faults() -> None:
    monitor = TemperatureMonitor(default_thresholds())
    verdict = monitor.evaluate([MotorThermal(drive_c=116.0, coil_c=50.0)])
    assert verdict.faulted
    causes = {(c.channel, c.severity) for c in verdict.fault_causes}
    assert ("drive", TempSeverity.FAULT) in causes


def test_coil_over_cap_reading_faults() -> None:
    monitor = TemperatureMonitor(default_thresholds())
    verdict = monitor.evaluate([MotorThermal(drive_c=40.0, coil_c=96.0)])
    assert verdict.faulted
    causes = {(c.channel, c.severity) for c in verdict.fault_causes}
    assert ("coil", TempSeverity.FAULT) in causes


def test_warn_band_warns_without_faulting() -> None:
    monitor = TemperatureMonitor(default_thresholds())
    verdict = monitor.evaluate([MotorThermal(drive_c=105.0, coil_c=50.0)])
    assert verdict.warned
    assert not verdict.faulted


def test_cool_readings_are_clean() -> None:
    monitor = TemperatureMonitor(default_thresholds())
    verdict = monitor.evaluate([MotorThermal(drive_c=40.0, coil_c=30.0)])
    assert not verdict.faulted
    assert not verdict.warned


def test_fault_names_the_offending_motor_index() -> None:
    monitor = TemperatureMonitor(default_thresholds())
    thermals = [
        MotorThermal(drive_c=40.0, coil_c=30.0),
        MotorThermal(drive_c=40.0, coil_c=30.0),
        MotorThermal(drive_c=118.0, coil_c=30.0),
    ]
    verdict = monitor.evaluate(thermals)
    assert verdict.faulted
    assert {c.motor_index for c in verdict.fault_causes} == {2}
