"""`MOTOR_LIMIT_PARAMS` and the RID 21/22/23 vs constant comparison (`03` FR-MOT-003).

`MOTOR_LIMIT_PARAMS` (`dm_motor_constants.hpp`) is the CAN-frame encoding range
`{PMAX, VMAX, TMAX}` per motor type — not a safety torque limit (`03` §2.2). If a
motor's internally stored RID 21/22/23 disagree with this table, position, speed
and torque scaling are all wrong, so `03` FR-MOT-003 / `12` FR-SAF-004 require the
read-back to be compared against it and torque blocked on any mismatch.

`DM3507` is here for exactly one reason: it is the *wrong* answer for J7. Its
TMAX is 5 Nm against DM4310's 10 Nm, so a J7 mis-registered as DM3507 makes every
MIT torque command and feedback off by 2x (`03` §2.1). Keeping DM3507 in the table
lets the J7 judgment (`judge.py`) name what it found rather than only that it was
not DM4310.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.can.rid.decoder import RidValue
from backend.can.rid.registers import RID_PMAX, RID_TMAX, RID_VMAX


class MotorType(Enum):
    """A Damiao motor type present on (or mis-attributed to) the OpenArm."""

    DM4310 = "DM4310"
    DM4340 = "DM4340"
    DM8009 = "DM8009"
    # Not on the arm: the MJCF-only mis-registration for J7 (`03` §2.1, `09` §2.6).
    DM3507 = "DM3507"


@dataclass(frozen=True)
class LimitParam:
    """The `{PMAX, VMAX, TMAX}` CAN-frame encoding range for one motor type.

    Attributes:
        p_max: Position scale limit (rad), RID 21.
        v_max: Velocity scale limit (rad/s), RID 22.
        t_max: Torque scale limit (Nm), RID 23.
    """

    p_max: float
    v_max: float
    t_max: float


# `03` §2.2 / `dm_motor_constants.hpp`. Values are the CAN encoding ranges, not
# physical safety limits (peak torque is a separate, smaller clamp, `03` FR-MOT-037).
MOTOR_LIMIT_PARAMS: dict[MotorType, LimitParam] = {
    MotorType.DM4310: LimitParam(p_max=12.5, v_max=30.0, t_max=10.0),
    MotorType.DM4340: LimitParam(p_max=12.5, v_max=8.0, t_max=28.0),
    MotorType.DM8009: LimitParam(p_max=12.5, v_max=45.0, t_max=54.0),
    MotorType.DM3507: LimitParam(p_max=12.5, v_max=50.0, t_max=5.0),
}

# A read-back never lands exactly on the constant in floating point, so the
# comparison is within a small absolute tolerance. This is a match window, not a
# safety margin; it only absorbs float32 round-trip noise.
LIMIT_MATCH_TOLERANCE = 1e-3


@dataclass(frozen=True)
class FieldComparison:
    """One RID's read-back against its expected constant.

    Attributes:
        rid: The register id (21, 22 or 23).
        field: The limit field name (`p_max` / `v_max` / `t_max`).
        expected: The `MOTOR_LIMIT_PARAMS` value for the expected motor type.
        actual: The value decoded from the motor.
        matches: True when `actual` equals `expected` within tolerance.
    """

    rid: int
    field: str
    expected: float
    actual: float
    matches: bool


@dataclass(frozen=True)
class LimitComparison:
    """The full RID 21/22/23 comparison for one motor (`03` FR-MOT-003).

    Attributes:
        motor_id: The CAN id of the motor.
        expected_type: The motor type the arm registration expects here.
        fields: Per-field comparisons for PMAX/VMAX/TMAX.
    """

    motor_id: int
    expected_type: MotorType
    fields: tuple[FieldComparison, ...]

    @property
    def matches(self) -> bool:
        """Report whether every compared field matched.

        Returns:
            (bool) True only when all of PMAX/VMAX/TMAX matched; False means
            torque must be blocked (`03` FR-MOT-003).
        """
        return all(field.matches for field in self.fields)

    def mismatches(self) -> tuple[FieldComparison, ...]:
        """Return only the fields that disagreed with the constant.

        Returns:
            (tuple[FieldComparison, ...]) The mismatching field comparisons.
        """
        return tuple(field for field in self.fields if not field.matches)


def _close(actual: float, expected: float) -> bool:
    """Report whether two limit values agree within the match tolerance.

    Args:
        actual: The decoded value.
        expected: The constant.

    Returns:
        (bool) True when the absolute difference is within tolerance.
    """
    return abs(actual - expected) <= LIMIT_MATCH_TOLERANCE


def compare_limits(
    motor_id: int,
    expected_type: MotorType,
    pmax: RidValue,
    vmax: RidValue,
    tmax: RidValue,
) -> LimitComparison:
    """Compare a motor's decoded RID 21/22/23 against `MOTOR_LIMIT_PARAMS`.

    Args:
        motor_id: The CAN id of the motor.
        expected_type: The motor type the arm registration expects at this id.
        pmax: Decoded RID 21 value.
        vmax: Decoded RID 22 value.
        tmax: Decoded RID 23 value.

    Returns:
        (LimitComparison) Per-field match report; `.matches` is the torque gate.

    Raises:
        ValueError: If any passed `RidValue` is not the RID it is meant to be.
    """
    for got, want in ((pmax.rid, RID_PMAX), (vmax.rid, RID_VMAX), (tmax.rid, RID_TMAX)):
        if got != want:
            raise ValueError(f"expected RID {want} for comparison, got RID {got}")
    limit = MOTOR_LIMIT_PARAMS[expected_type]
    fields = (
        FieldComparison(
            rid=RID_PMAX,
            field="p_max",
            expected=limit.p_max,
            actual=float(pmax.value),
            matches=_close(float(pmax.value), limit.p_max),
        ),
        FieldComparison(
            rid=RID_VMAX,
            field="v_max",
            expected=limit.v_max,
            actual=float(vmax.value),
            matches=_close(float(vmax.value), limit.v_max),
        ),
        FieldComparison(
            rid=RID_TMAX,
            field="t_max",
            expected=limit.t_max,
            actual=float(tmax.value),
            matches=_close(float(tmax.value), limit.t_max),
        ),
    )
    return LimitComparison(motor_id=motor_id, expected_type=expected_type, fields=fields)
