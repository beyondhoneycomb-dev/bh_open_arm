"""Judgment scaffolds for the three RID gates: PG-J7-001, PG-VMAX-001, PG-RID-001.

Each function here is a pure decision over already-decoded read-backs — the logic a
gate applies once real values exist. The values themselves come from 16 powered
motors (torque-OFF asserted first, `12` FR-SAF-075), which this host cannot
produce, so the *judgment* runs and is unit-tested on synthetic values here while
the *acceptance* (feeding it real captures) is deferred to the re-verification hook.

- `judge_j7` (`03` FR-MOT-004): RID 23 TMAX classifies J7's motor type. 10 Nm is
  DM4310 (PASS); 5 Nm is DM3507, a mis-registration that makes MIT torque off by
  2x, so it fails blocking and triggers the `WP-0C-03` MJCF fix before friction
  identification is poisoned.
- `judge_vmax` (`16` §3.1): DM4340 RID 22 VMAX classifies 8 / 10 / 20, which only
  rescales commands; the supply voltage must be recorded alongside.
- `judge_rid9_timeout` (`16` M-4, `12` NFR-SAF-007): RID 9 across all motors. A
  partial read forbids torque-ON (`PG-RID-001` FAIL_BLOCKING); a zero, a value at
  or under the send-period margin, or heterogeneous values each pick a branch.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.can.rid.layout import J7_EXPECTED_TYPE
from backend.can.rid.motor_limits import MOTOR_LIMIT_PARAMS, MotorType
from backend.can.rid.registers import TIMEOUT_LSB_MICROSECONDS


class PgStatus(Enum):
    """The outcome of a gate judgment."""

    PASS = "PASS"
    FAIL_BLOCKING = "FAIL_BLOCKING"
    PENDING = "PENDING"


# TMAX read-back must land within this Nm window of a type's stored TMAX to be
# classified as that type. The DM4310 (10) vs DM3507 (5) gap is 5 Nm, so this
# window separates them with wide room while absorbing float32 noise.
TMAX_CLASSIFY_TOLERANCE = 0.5

# The DM4340 VMAX variants that a 24V/48V / motorbridge configuration can produce
# (`16` §3.1): stock 8, `4340P` 10, `4340_v20` 20.
DM4340_VMAX_VARIANTS: tuple[float, ...] = (8.0, 10.0, 20.0)
VMAX_CLASSIFY_TOLERANCE = 0.5


@dataclass(frozen=True)
class J7Judgment:
    """PG-J7-001 outcome from J7's RID 23 TMAX read-back.

    Attributes:
        status: PASS when J7 is DM4310, else FAIL_BLOCKING.
        measured_tmax: The decoded RID 23 value.
        classified_type: The motor type the TMAX matches, or None if it matches
            no known type within tolerance.
        expected_type: The registered J7 type (DM4310).
        triggers_wp0c03: True when the mismatch must trigger the `WP-0C-03` MJCF
            asset fix before friction identification runs.
    """

    status: PgStatus
    measured_tmax: float
    classified_type: MotorType | None
    expected_type: MotorType
    triggers_wp0c03: bool


def _classify_by_tmax(tmax: float) -> MotorType | None:
    """Return the motor type whose stored TMAX matches a read-back, if any.

    Args:
        tmax: The decoded RID 23 value.

    Returns:
        (MotorType | None) The matching type within tolerance, else None.
    """
    for motor_type, limit in MOTOR_LIMIT_PARAMS.items():
        if abs(tmax - limit.t_max) <= TMAX_CLASSIFY_TOLERANCE:
            return motor_type
    return None


def judge_j7(measured_tmax: float) -> J7Judgment:
    """Judge PG-J7-001 from J7's RID 23 TMAX (`03` FR-MOT-004).

    Args:
        measured_tmax: The decoded RID 23 value read from J7.

    Returns:
        (J7Judgment) PASS only when the TMAX classifies as DM4310; otherwise
        FAIL_BLOCKING with `triggers_wp0c03` set.
    """
    classified = _classify_by_tmax(measured_tmax)
    is_expected = classified is J7_EXPECTED_TYPE
    return J7Judgment(
        status=PgStatus.PASS if is_expected else PgStatus.FAIL_BLOCKING,
        measured_tmax=measured_tmax,
        classified_type=classified,
        expected_type=J7_EXPECTED_TYPE,
        triggers_wp0c03=not is_expected,
    )


@dataclass(frozen=True)
class VmaxJudgment:
    """PG-VMAX-001 outcome from a DM4340's RID 22 VMAX read-back (`16` §3.1).

    Attributes:
        measured_vmax: The decoded RID 22 value.
        classified_variant: The nearest of 8 / 10 / 20, or None if none within
            tolerance.
        supply_voltage_required: Always True — the variant only means something
            recorded next to the real supply voltage; VMAX alone does not gate.
    """

    measured_vmax: float
    classified_variant: float | None
    supply_voltage_required: bool


def judge_vmax(measured_vmax: float) -> VmaxJudgment:
    """Classify a DM4340 RID 22 VMAX among the 8 / 10 / 20 variants.

    Args:
        measured_vmax: The decoded RID 22 value read from a DM4340 joint.

    Returns:
        (VmaxJudgment) The classified variant (or None) plus the standing
        requirement to record the supply voltage.
    """
    nearest = min(
        DM4340_VMAX_VARIANTS,
        key=lambda variant: abs(measured_vmax - variant),
    )
    within = abs(measured_vmax - nearest) <= VMAX_CLASSIFY_TOLERANCE
    return VmaxJudgment(
        measured_vmax=measured_vmax,
        classified_variant=nearest if within else None,
        supply_voltage_required=True,
    )


class Rid9Branch(Enum):
    """The per-motor RID 9 timeout branch (`16` M-4)."""

    HW_FALLBACK_DISABLED = "hw_fallback_disabled"  # value 0.
    RAISE_TX_OR_NORMALIZE = "raise_tx_or_normalize"  # value at or under the margin.
    ADEQUATE = "adequate"  # value clears the send-period margin.


@dataclass(frozen=True)
class MotorTimeout:
    """One motor's RID 9 timeout classification.

    Attributes:
        motor_id: The CAN send id.
        raw_lsb: The decoded uint32 timeout in 50 us LSBs.
        microseconds: The timeout in microseconds.
        branch: The branch this value selects.
    """

    motor_id: int
    raw_lsb: int
    microseconds: int
    branch: Rid9Branch


@dataclass(frozen=True)
class Rid9Judgment:
    """PG-RID-001 outcome over the RID 9 read of every expected motor.

    Attributes:
        status: FAIL_BLOCKING on any missing motor (partial read = no torque-ON);
            else PASS once every motor was read.
        missing_motor_ids: Expected motors whose RID 9 was not read.
        per_motor: Per-motor classification for the motors that were read.
        heterogeneous: True when the read motors do not all share one timeout —
            the "min-value design or block" branch.
    """

    status: PgStatus
    missing_motor_ids: tuple[int, ...]
    per_motor: tuple[MotorTimeout, ...]
    heterogeneous: bool


def judge_rid9_timeout(
    expected_motor_ids: tuple[int, ...],
    observed: dict[int, int],
    margin_lsb: int,
) -> Rid9Judgment:
    """Judge PG-RID-001 from the RID 9 timeout read of every expected motor.

    Args:
        expected_motor_ids: Every motor a full read must cover (16 on the rig).
        observed: motor_id -> decoded uint32 timeout in 50 us LSBs, for the
            motors that were read. A missing key is a read failure.
        margin_lsb: The send-period margin in the same 50 us LSBs; a timeout at or
            under it selects the raise-tx-or-normalize branch.

    Returns:
        (Rid9Judgment) FAIL_BLOCKING when any expected motor is missing (`03`
        FR-MOT-003 read-failure = torque-ON forbidden); else PASS with the
        per-motor branches and the heterogeneity flag.
    """
    missing = tuple(mid for mid in expected_motor_ids if mid not in observed)
    per_motor = tuple(
        MotorTimeout(
            motor_id=mid,
            raw_lsb=observed[mid],
            microseconds=observed[mid] * TIMEOUT_LSB_MICROSECONDS,
            branch=_rid9_branch(observed[mid], margin_lsb),
        )
        for mid in expected_motor_ids
        if mid in observed
    )
    heterogeneous = len({m.raw_lsb for m in per_motor}) > 1
    status = PgStatus.FAIL_BLOCKING if missing else PgStatus.PASS
    return Rid9Judgment(
        status=status,
        missing_motor_ids=missing,
        per_motor=per_motor,
        heterogeneous=heterogeneous,
    )


def _rid9_branch(value_lsb: int, margin_lsb: int) -> Rid9Branch:
    """Select the RID 9 branch for one timeout value.

    Args:
        value_lsb: The decoded timeout in 50 us LSBs.
        margin_lsb: The send-period margin in the same LSBs.

    Returns:
        (Rid9Branch) The branch this value falls in.
    """
    if value_lsb == 0:
        return Rid9Branch.HW_FALLBACK_DISABLED
    if value_lsb <= margin_lsb:
        return Rid9Branch.RAISE_TX_OR_NORMALIZE
    return Rid9Branch.ADEQUATE
