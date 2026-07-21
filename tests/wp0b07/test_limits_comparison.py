"""Acceptance ③ — RID 21/22/23 decoded and compared against `MOTOR_LIMIT_PARAMS`.

Runs here: the comparison is pure decode + table lookup, no motor needed. The
deferred part is only feeding it the real 16-motor read-back (①/reverify hook).
"""

from __future__ import annotations

from backend.can.rid.dump import parse_dump
from backend.can.rid.evaluate import evaluate_dump
from backend.can.rid.motor_limits import (
    MOTOR_LIMIT_PARAMS,
    LimitParam,
    MotorType,
    compare_limits,
)
from backend.can.rid.registers import RID_PMAX, RID_TMAX, RID_VMAX
from tests.wp0b07 import rid_fixtures as fx

_DEFAULT_MARGIN_LSB = 20


def _decode_limits(motor_type: MotorType, actual: LimitParam) -> tuple[object, object, object]:
    body = fx.motor_with_limits(expected_type=motor_type, actual=actual)
    dump = parse_dump(fx.dump("oa_fl", {0x05: body}))
    motor = dump.motors[0x05]
    return motor.decoded(RID_PMAX), motor.decoded(RID_VMAX), motor.decoded(RID_TMAX)


def test_dm4310_readback_matches_constant() -> None:
    pmax, vmax, tmax = _decode_limits(MotorType.DM4310, MOTOR_LIMIT_PARAMS[MotorType.DM4310])
    result = compare_limits(0x05, MotorType.DM4310, pmax, vmax, tmax)  # type: ignore[arg-type]
    assert result.matches
    assert result.mismatches() == ()


def test_dm4340_readback_matches_constant() -> None:
    pmax, vmax, tmax = _decode_limits(MotorType.DM4340, MOTOR_LIMIT_PARAMS[MotorType.DM4340])
    result = compare_limits(0x03, MotorType.DM4340, pmax, vmax, tmax)  # type: ignore[arg-type]
    assert result.matches


def test_mismatch_reports_every_offending_field() -> None:
    # A motor registered DM4310 but reporting DM3507 limits (the J7 mis-registration
    # shape): PMAX still 12.5 (match), but VMAX 50!=30 and TMAX 5!=10 both mismatch.
    pmax, vmax, tmax = _decode_limits(MotorType.DM4310, MOTOR_LIMIT_PARAMS[MotorType.DM3507])
    result = compare_limits(0x07, MotorType.DM4310, pmax, vmax, tmax)  # type: ignore[arg-type]
    assert not result.matches
    offending = {field.rid for field in result.mismatches()}
    assert offending == {RID_VMAX, RID_TMAX}
    assert RID_PMAX not in offending
    tmax_field = next(field for field in result.mismatches() if field.rid == RID_TMAX)
    assert tmax_field.expected == 10.0
    assert tmax_field.actual == 5.0


def test_evaluate_dump_flags_the_mismatching_motor() -> None:
    good = fx.healthy_motor(MotorType.DM4310, timeout_lsb=1000)
    bad = fx.motor_with_limits(MotorType.DM4310, MOTOR_LIMIT_PARAMS[MotorType.DM3507])
    dump = parse_dump(fx.dump("oa_fl", {0x05: good, 0x07: bad}))
    evaluation = evaluate_dump(dump, _DEFAULT_MARGIN_LSB)
    by_id = {m.motor_id: m for m in evaluation.per_motor}
    assert by_id[0x05].limits is not None and by_id[0x05].limits.matches
    assert by_id[0x07].limits is not None and not by_id[0x07].limits.matches
