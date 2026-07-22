"""Shared builders for the WP-2D-04 acceptance tests.

A synthetic seven-joint wall set (symmetric limits, a known effort table) makes the
repulsion geometry checkable without the robot stack, and a healthy/enable status byte plus
a Freedrive detection suite over the reused watchdog and temperature monitor make the
detection switch checkable without a bus. The committed cell asset is loaded only where the
Cartesian keep-out reuse is under test.
"""

from __future__ import annotations

from pathlib import Path

from backend.actuation import (
    ManualClock,
    SafetyLatch,
    UnknownErrNibbleError,
    decode_motor_err,
)
from backend.commloss import CommLossWatchdog
from backend.freedrive_walls import (
    FreedriveDetectionSuite,
    FreedriveResidualPolicy,
    JointLimitRepulsion,
    JointWall,
)
from backend.temp_gripper import MotorThermal, TemperatureMonitor, default_thresholds

# A symmetric +-1 rad range on every joint, with the canonical URDF effort table, so a
# repulsion built here has a known interior (zero torque) and known caps.
SYNTHETIC_LOWER_RAD = (-1.0,) * 7
SYNTHETIC_UPPER_RAD = (1.0,) * 7
SYNTHETIC_EFFORT_NM = (40.0, 40.0, 27.0, 27.0, 7.0, 7.0, 7.0)

COMM_TIMEOUT_SEC = 0.01


def synthetic_repulsion(fraction: float = 0.5, band_rad: float = 0.0873) -> JointLimitRepulsion:
    """Build a seven-joint repulsion field over the synthetic walls.

    Args:
        fraction: Share of each joint's effort the wall may spend at the hardstop.
        band_rad: Near-limit band, radians (default ~5 deg).

    Returns:
        (JointLimitRepulsion) The synthetic-wall repulsion field.
    """
    walls = tuple(
        JointWall(low, high, effort, effort * fraction)
        for low, high, effort in zip(
            SYNTHETIC_LOWER_RAD, SYNTHETIC_UPPER_RAD, SYNTHETIC_EFFORT_NM, strict=True
        )
    )
    return JointLimitRepulsion(walls, band_rad)


def healthy_status_byte() -> int:
    """Return a Damiao status byte the ERR decoder reads as a non-fault (enable baseline)."""
    return next(byte for byte in range(256) if not decode_motor_err(byte).is_fault)


def fault_status_byte() -> int:
    """Return a Damiao status byte carrying a fault ERR nibble.

    The reused decoder raises on a nibble it cannot vouch for, so the scan skips those and
    returns the first byte the decoder positively grades as a fault.
    """
    for byte in range(256):
        try:
            if decode_motor_err(byte).is_fault:
                return byte
        except UnknownErrNibbleError:
            continue
    raise AssertionError("no fault ERR-nibble status byte exists in [0, 256)")


def ok_thermals() -> tuple[MotorThermal, ...]:
    """Return seven cool per-motor thermals (no over-temperature)."""
    return tuple(MotorThermal(drive_c=30.0, coil_c=30.0) for _ in range(7))


def freedrive_suite(
    residual_policy: FreedriveResidualPolicy | None = None,
) -> tuple[CommLossWatchdog, ManualClock, FreedriveDetectionSuite]:
    """Build a detection suite over a fresh reused watchdog and temperature monitor.

    Args:
        residual_policy: The Freedrive residual policy; a suppressed policy by default.

    Returns:
        (CommLossWatchdog) The reused watchdog.
        (ManualClock) The watchdog's clock, for advancing past the comm-loss timeout.
        (FreedriveDetectionSuite) The suite over the synthetic soft-limit bounds.
    """
    clock = ManualClock()
    watchdog = CommLossWatchdog(SafetyLatch(), clock, comm_timeout_sec=COMM_TIMEOUT_SEC)
    suite = FreedriveDetectionSuite(
        residual_policy or FreedriveResidualPolicy(),
        watchdog,
        TemperatureMonitor(default_thresholds()),
        SYNTHETIC_LOWER_RAD,
        SYNTHETIC_UPPER_RAD,
    )
    return watchdog, clock, suite


def committed_cell_path() -> Path:
    """Return the committed v2 cell asset path (WP-0C-03, read-only)."""
    import sim.mjcf

    return Path(sim.mjcf.__file__).resolve().parent / "v2" / "cell.xml"
