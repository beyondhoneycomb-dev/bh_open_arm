"""Zero-residual verification for the OpenArm follower (02 FR-CON-065).

After a 0xFE set-zero, the raw joint angles read back should match the expected
URDF-zero reference within a per-joint tolerance (default ±0.5°). The same check runs
in two places against the same reference: immediately after set-zero (FR-CON-065 ②),
and again after a power cycle to test whether the 0xFE zero persisted (FR-CON-065 ③).

The check is pure arithmetic over two vectors and a tolerance, so it runs fully
offline; only the readback that feeds it comes from hardware.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.calibration.schema import MOTOR_COUNT, MOTOR_ORDER, ZERO_RESIDUAL_TOLERANCE_DEG


@dataclass(frozen=True)
class ResidualResult:
    """The outcome of a zero-residual check.

    Attributes:
        residual_deg: Signed per-motor residual (measured - reference), in degrees.
        tolerance_deg: The per-joint tolerance applied.
        within_tolerance: True when every joint's absolute residual is within tolerance.
        offenders: Names of the motors that exceeded tolerance, in MOTOR_ORDER order.
    """

    residual_deg: list[float]
    tolerance_deg: float
    within_tolerance: bool
    offenders: tuple[str, ...]


def compute_residual(
    measured_deg: list[float],
    urdf_zero_offset_deg: list[float],
    tolerance_deg: float = ZERO_RESIDUAL_TOLERANCE_DEG,
) -> ResidualResult:
    """Compute the per-joint zero residual and whether it is within tolerance.

    Args:
        measured_deg: Raw joint angles (degrees) read back after set-zero, per motor.
        urdf_zero_offset_deg: Expected URDF-zero angles (degrees), per motor.
        tolerance_deg: Per-joint tolerance (degrees); defaults to the FR-CON-065 ±0.5°.

    Returns:
        (ResidualResult) The residual vector and pass/fail with named offenders.

    Raises:
        ValueError: If either vector is not MOTOR_COUNT long.
    """
    if len(measured_deg) != MOTOR_COUNT or len(urdf_zero_offset_deg) != MOTOR_COUNT:
        raise ValueError(
            f"residual needs two {MOTOR_COUNT}-vectors, got "
            f"{len(measured_deg)} and {len(urdf_zero_offset_deg)}"
        )
    residual = [
        float(m) - float(r) for m, r in zip(measured_deg, urdf_zero_offset_deg, strict=True)
    ]
    offenders = tuple(
        MOTOR_ORDER[i] for i, value in enumerate(residual) if abs(value) > tolerance_deg
    )
    return ResidualResult(
        residual_deg=residual,
        tolerance_deg=tolerance_deg,
        within_tolerance=not offenders,
        offenders=offenders,
    )
