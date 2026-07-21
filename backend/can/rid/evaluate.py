"""Run the full RID judgment suite over one dump — synthetic here, real via the hook.

`evaluate_dump` is the one place the whole judgment is assembled: type-misread
detection, the RID 9 timeout branch, the RID 21/22/23 limit comparison per motor,
the J7 TMAX judgment, the DM4340 VMAX classification, and the protection-threshold
record. The synthetic acceptances (③, ⑦) call it here; the re-verification hook
(`reverify.py`) calls the identical function against a real 16-motor capture, so the
deferred acceptances (①②④⑤⑥) re-run this exact code the moment real bytes exist.

Nothing here reaches hardware or asserts a pass — it decodes and judges whatever
dump it is handed. Whether the values came from a fixture or a powered rig is the
caller's concern, which is what keeps the synthetic run and the deferred run honest.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.can.rid.decoder import RidValue, TypeMisread, find_type_misreads
from backend.can.rid.dump import RidDump
from backend.can.rid.judge import (
    J7Judgment,
    Rid9Judgment,
    VmaxJudgment,
    judge_j7,
    judge_rid9_timeout,
    judge_vmax,
)
from backend.can.rid.layout import (
    ARM_SEND_IDS,
    DM4340_MOTOR_IDS,
    J7_MOTOR_ID,
    expected_type,
)
from backend.can.rid.motor_limits import LimitComparison, MotorType, compare_limits
from backend.can.rid.registers import (
    RID_OC,
    RID_OT,
    RID_OV,
    RID_PMAX,
    RID_TIMEOUT,
    RID_TMAX,
    RID_UV,
    RID_VMAX,
)

# The protection-threshold registers recorded for acceptance ⑥ (`03` FR-MOT-039).
PROTECTION_RIDS: tuple[int, ...] = (RID_UV, RID_OT, RID_OC, RID_OV)


@dataclass(frozen=True)
class MotorEvaluation:
    """The per-motor slice of a dump evaluation.

    Attributes:
        motor_id: The CAN send id.
        expected_type: The registered motor type used for the limit comparison.
        limits: The RID 21/22/23 comparison, or None when those RIDs were unread.
        protection: Decoded UV/OT/OC/OV values that were read, by RID (⑥).
    """

    motor_id: int
    expected_type: MotorType
    limits: LimitComparison | None
    protection: dict[int, RidValue]


@dataclass(frozen=True)
class DumpEvaluation:
    """The full judgment over one interface's dump.

    Attributes:
        iface: The interface the dump was captured on.
        misreads: Type-misread findings across every read register (⑦).
        rid9: The RID 9 timeout / PG-RID-001 judgment over the arm (①②).
        per_motor: Per-motor limit and protection evaluations (③⑥).
        j7: J7's TMAX / PG-J7-001 judgment, when J7 RID 23 was read (④).
        vmax: DM4340 VMAX / PG-VMAX-001 judgments by motor id (⑤).
    """

    iface: str
    misreads: tuple[TypeMisread, ...]
    rid9: Rid9Judgment
    per_motor: tuple[MotorEvaluation, ...]
    j7: J7Judgment | None
    vmax: dict[int, VmaxJudgment]


def _expected_type_for(dump: RidDump, motor_id: int) -> MotorType:
    """Return the expected motor type for a motor, dump-pinned or from the layout.

    Args:
        dump: The dump under evaluation.
        motor_id: The CAN send id.

    Returns:
        (MotorType) The dump's pinned type when present, else the registered type.
    """
    pinned = dump.motors[motor_id].expected_type
    return pinned if pinned is not None else expected_type(motor_id)


def _evaluate_motor(dump: RidDump, motor_id: int) -> MotorEvaluation:
    """Evaluate one motor's limits and protection registers.

    Args:
        dump: The dump under evaluation.
        motor_id: The CAN send id.

    Returns:
        (MotorEvaluation) The per-motor limit comparison and protection record.
    """
    motor = dump.motors[motor_id]
    want_type = _expected_type_for(dump, motor_id)
    limits: LimitComparison | None = None
    if all(motor.has(rid) for rid in (RID_PMAX, RID_VMAX, RID_TMAX)):
        limits = compare_limits(
            motor_id=motor_id,
            expected_type=want_type,
            pmax=motor.decoded(RID_PMAX),
            vmax=motor.decoded(RID_VMAX),
            tmax=motor.decoded(RID_TMAX),
        )
    protection = {rid: motor.decoded(rid) for rid in PROTECTION_RIDS if motor.has(rid)}
    return MotorEvaluation(
        motor_id=motor_id,
        expected_type=want_type,
        limits=limits,
        protection=protection,
    )


def evaluate_dump(dump: RidDump, margin_lsb: int) -> DumpEvaluation:
    """Run the full RID judgment suite over one interface's dump.

    Args:
        dump: The decoded read-backs for one interface.
        margin_lsb: The RID 9 send-period margin in 50 us LSBs.

    Returns:
        (DumpEvaluation) Misreads, the RID 9 judgment, per-motor limit/protection
        evaluations, the J7 judgment (when read), and DM4340 VMAX judgments.
    """
    misreads = tuple(find_type_misreads(dump.all_misread_entries()))

    observed_rid9 = {
        mid: int(dump.motors[mid].decoded(RID_TIMEOUT).value)
        for mid in dump.motor_ids()
        if dump.motors[mid].has(RID_TIMEOUT)
    }
    rid9 = judge_rid9_timeout(ARM_SEND_IDS, observed_rid9, margin_lsb)

    per_motor = tuple(_evaluate_motor(dump, mid) for mid in dump.motor_ids())

    j7: J7Judgment | None = None
    if J7_MOTOR_ID in dump.motors and dump.motors[J7_MOTOR_ID].has(RID_TMAX):
        j7 = judge_j7(float(dump.motors[J7_MOTOR_ID].decoded(RID_TMAX).value))

    vmax = {
        mid: judge_vmax(float(dump.motors[mid].decoded(RID_VMAX).value))
        for mid in DM4340_MOTOR_IDS
        if mid in dump.motors and dump.motors[mid].has(RID_VMAX)
    }

    return DumpEvaluation(
        iface=dump.iface,
        misreads=misreads,
        rid9=rid9,
        per_motor=per_motor,
        j7=j7,
        vmax=vmax,
    )
