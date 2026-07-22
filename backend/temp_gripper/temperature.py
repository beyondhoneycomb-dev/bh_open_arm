"""Per-motor driver/coil over-temperature detection with FR-SAF-026 fault caps.

The fault threshold for each channel is capped below the motor's own self-protection
(driver 120 °C fixed, coil ≤100 °C) so the arm is held under command before the motor
drops its own enable — a self-disable at temperature is exactly the brakeless fall this
monitor pre-empts (spec 12 §2.2, FR-SAF-026). A fault therefore signals a Cat-2 hold to
the safety layer; this module never disables torque itself.

Detection only: it turns a per-motor temperature reading into a verdict. Engaging the
hold is the scheduler's continuous STOP_HOLD (WP-2C-05), not this module — a torque-off
here would be the drop it guards against. The excitation session's single 80 °C abort
ceiling (WP-2B-06, `DEFAULT_MAX_MOTOR_TEMP_C`) is a separate, more conservative
identification-time limit and is deliberately not this fault cap.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from backend.temp_gripper.constants import (
    COIL_CHANNEL,
    COIL_TEMP_FAULT_CAP_C,
    COIL_TEMP_WARN_DEFAULT_C,
    DRIVE_CHANNEL,
    DRIVE_TEMP_FAULT_CAP_C,
    DRIVE_TEMP_WARN_DEFAULT_C,
)
from backend.temp_gripper.errors import TempGripperConfigError
from backend.temp_gripper.feedback import MotorThermal


class TempSeverity(Enum):
    """The severity a single thermal-channel reading falls into."""

    OK = "ok"
    WARN = "warn"
    FAULT = "fault"


@dataclass(frozen=True)
class TemperatureThresholds:
    """Per-channel warn/fault temperatures, °C, with the FR-SAF-026 fault caps enforced.

    The fault temperatures are capped at the ceilings (driver `DRIVE_TEMP_FAULT_CAP_C`,
    coil `COIL_TEMP_FAULT_CAP_C`); a fault set above its cap is refused, not silently
    clamped, so a config can never move the hold past the point where the motor
    self-disables. Warn must sit strictly below fault on each channel.

    Attributes:
        drive_warn_c: Driver (T_MOS) warn threshold, °C.
        drive_fault_c: Driver (T_MOS) fault threshold, °C; must be ≤ the driver cap.
        coil_warn_c: Coil (T_Rotor) warn threshold, °C.
        coil_fault_c: Coil (T_Rotor) fault threshold, °C; must be ≤ the coil cap.
    """

    drive_warn_c: float
    drive_fault_c: float
    coil_warn_c: float
    coil_fault_c: float

    def __post_init__(self) -> None:
        """Refuse any fault above its cap or any warn not below its fault."""
        if self.drive_fault_c > DRIVE_TEMP_FAULT_CAP_C:
            raise TempGripperConfigError(
                f"driver fault threshold {self.drive_fault_c} exceeds the FR-SAF-026 cap "
                f"{DRIVE_TEMP_FAULT_CAP_C}"
            )
        if self.coil_fault_c > COIL_TEMP_FAULT_CAP_C:
            raise TempGripperConfigError(
                f"coil fault threshold {self.coil_fault_c} exceeds the FR-SAF-026 cap "
                f"{COIL_TEMP_FAULT_CAP_C}"
            )
        if not self.drive_warn_c < self.drive_fault_c:
            raise TempGripperConfigError(
                f"driver warn {self.drive_warn_c} must be below fault {self.drive_fault_c}"
            )
        if not self.coil_warn_c < self.coil_fault_c:
            raise TempGripperConfigError(
                f"coil warn {self.coil_warn_c} must be below fault {self.coil_fault_c}"
            )


def default_thresholds() -> TemperatureThresholds:
    """Return the default thresholds: warn margins under the FR-SAF-026 fault caps."""
    return TemperatureThresholds(
        drive_warn_c=DRIVE_TEMP_WARN_DEFAULT_C,
        drive_fault_c=DRIVE_TEMP_FAULT_CAP_C,
        coil_warn_c=COIL_TEMP_WARN_DEFAULT_C,
        coil_fault_c=COIL_TEMP_FAULT_CAP_C,
    )


@dataclass(frozen=True)
class ChannelReading:
    """The graded severity of one motor's one thermal channel.

    Attributes:
        motor_index: 0-based index of the motor in the evaluated sequence.
        channel: `DRIVE_CHANNEL` or `COIL_CHANNEL`.
        temperature_c: The reading, °C.
        severity: OK, WARN, or FAULT against the thresholds.
    """

    motor_index: int
    channel: str
    temperature_c: float
    severity: TempSeverity


@dataclass(frozen=True)
class TemperatureVerdict:
    """The whole-arm verdict for one set of per-motor thermal readings.

    Attributes:
        faulted: Whether any channel reached its fault threshold — a Cat-2 hold signal.
        warned: Whether any channel reached its warn threshold (and did not fault).
        fault_causes: The channel readings at FAULT severity.
        warn_causes: The channel readings at WARN severity.
    """

    faulted: bool
    warned: bool
    fault_causes: tuple[ChannelReading, ...]
    warn_causes: tuple[ChannelReading, ...]


class TemperatureMonitor:
    """Grades per-motor driver/coil temperatures against the capped thresholds.

    Ownership/threading: holds only the immutable thresholds; a single caller drives
    `evaluate` once per feedback cycle. It reads temperatures and returns a verdict,
    never touching the bus — the hold the fault signals is emitted downstream.
    """

    def __init__(self, thresholds: TemperatureThresholds) -> None:
        """Wire the monitor to a validated threshold set.

        Args:
            thresholds: The per-channel warn/fault temperatures (fault ≤ its cap).
        """
        self._thresholds = thresholds

    def _severity(self, temperature_c: float, warn_c: float, fault_c: float) -> TempSeverity:
        """Grade one temperature against a warn/fault pair (fault wins over warn)."""
        if temperature_c >= fault_c:
            return TempSeverity.FAULT
        if temperature_c >= warn_c:
            return TempSeverity.WARN
        return TempSeverity.OK

    def evaluate_motor(self, motor_index: int, thermal: MotorThermal) -> tuple[ChannelReading, ...]:
        """Grade one motor's driver and coil readings.

        Args:
            motor_index: 0-based index of the motor in the evaluated sequence.
            thermal: The motor's decoded driver and coil temperatures.

        Returns:
            (tuple) The driver reading then the coil reading.
        """
        drive = ChannelReading(
            motor_index,
            DRIVE_CHANNEL,
            thermal.drive_c,
            self._severity(
                thermal.drive_c, self._thresholds.drive_warn_c, self._thresholds.drive_fault_c
            ),
        )
        coil = ChannelReading(
            motor_index,
            COIL_CHANNEL,
            thermal.coil_c,
            self._severity(
                thermal.coil_c, self._thresholds.coil_warn_c, self._thresholds.coil_fault_c
            ),
        )
        return (drive, coil)

    def evaluate(self, thermals: Sequence[MotorThermal]) -> TemperatureVerdict:
        """Grade every motor's readings into a single whole-arm verdict.

        Args:
            thermals: Per-motor decoded thermals, in motor-index order.

        Returns:
            (TemperatureVerdict) The graded readings split into fault and warn causes.
        """
        readings: list[ChannelReading] = []
        for motor_index, thermal in enumerate(thermals):
            readings.extend(self.evaluate_motor(motor_index, thermal))
        faults = tuple(r for r in readings if r.severity is TempSeverity.FAULT)
        warns = tuple(r for r in readings if r.severity is TempSeverity.WARN)
        return TemperatureVerdict(
            faulted=bool(faults),
            warned=bool(warns),
            fault_causes=faults,
            warn_causes=warns,
        )
