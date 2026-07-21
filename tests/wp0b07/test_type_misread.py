"""Acceptance ⑦ — a value read under the wrong type is detected, not silently trusted.

A `uint32` timeout read as `float32` (or a `float32` limit read as `uint32`) is
plausible-looking garbage. The detection pins the type to the RID (`03` FR-MOT-010)
and flags any reading whose recorded type disagrees. Runs here entirely.
"""

from __future__ import annotations

import struct

from backend.can.rid.decoder import find_type_misreads
from backend.can.rid.dump import RidDump, parse_dump
from backend.can.rid.evaluate import evaluate_dump
from backend.can.rid.motor_limits import MotorType
from tests.wp0b07 import rid_fixtures as fx

_DEFAULT_MARGIN_LSB = 20


def _misread_dump() -> RidDump:
    # RID 9 (u32 timeout) recorded as f32, and RID 23 (f32 TMAX) recorded as u32 —
    # both declared types contradict the FR-MOT-010 rule.
    body = {
        "expected_type": "DM4310",
        "registers": {
            "9": fx.u32_hex(800),
            "23": fx.f32_hex(10.0),
        },
        "declared_kinds": {"9": "float32", "23": "uint32"},
    }
    return parse_dump(fx.dump("oa_fl", {0x05: body}))


def test_declared_type_contradicting_the_rule_is_flagged() -> None:
    misreads = find_type_misreads(_misread_dump().all_misread_entries())
    flagged = {(m.rid, m.declared_kind, m.mandated_kind) for m in misreads}
    assert (9, "f32", "u32") in flagged
    assert (23, "u32", "f32") in flagged


def test_misread_carries_both_interpretations_as_evidence() -> None:
    misreads = find_type_misreads(_misread_dump().all_misread_entries())

    rid9_bytes = bytes.fromhex(fx.u32_hex(800))
    rid9 = next(m for m in misreads if m.rid == 9)
    # Correct u32 read is 800; the same bytes read as f32 are a tiny denormal.
    assert rid9.as_mandated == 800
    assert rid9.as_declared == struct.unpack("<f", rid9_bytes)[0]

    rid23 = next(m for m in misreads if m.rid == 23)
    # Correct f32 read is 10.0; the same bytes read as u32 are the raw bit pattern.
    assert rid23.as_mandated == 10.0
    assert rid23.as_declared == struct.unpack("<I", bytes.fromhex(fx.f32_hex(10.0)))[0]


def test_correctly_typed_dump_has_no_misreads() -> None:
    dump = parse_dump(fx.dump("oa_fl", {0x05: fx.healthy_motor(MotorType.DM4310, 1000)}))
    assert find_type_misreads(dump.all_misread_entries()) == []
    # And the aggregate evaluation agrees.
    assert evaluate_dump(dump, _DEFAULT_MARGIN_LSB).misreads == ()
