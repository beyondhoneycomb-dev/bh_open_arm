"""The `03` FR-MOT-010 type rule and little-endian decode (foundation for ③ and ⑦)."""

from __future__ import annotations

import struct

import pytest

from backend.can.rid.decoder import decode, decode_as, mandated_kind
from backend.can.rid.registers import is_uint32_rid


@pytest.mark.parametrize("rid", [7, 8, 9, 10, 13, 14, 15, 16, 35, 36])
def test_uint32_ranges_are_u32(rid: int) -> None:
    assert is_uint32_rid(rid)
    assert mandated_kind(rid) == "u32"


@pytest.mark.parametrize("rid", [0, 1, 2, 3, 6, 11, 12, 17, 20, 21, 22, 23, 29, 34, 37, 50])
def test_everything_else_is_f32(rid: int) -> None:
    assert not is_uint32_rid(rid)
    assert mandated_kind(rid) == "f32"


def test_range_boundaries_are_closed() -> None:
    # The C++ predicate is inclusive on both ends: 7..10, 13..16, 35..36.
    assert mandated_kind(6) == "f32" and mandated_kind(7) == "u32"
    assert mandated_kind(10) == "u32" and mandated_kind(11) == "f32"
    assert mandated_kind(12) == "f32" and mandated_kind(13) == "u32"
    assert mandated_kind(16) == "u32" and mandated_kind(17) == "f32"
    assert mandated_kind(34) == "f32" and mandated_kind(35) == "u32"
    assert mandated_kind(36) == "u32" and mandated_kind(37) == "f32"


def test_decode_is_little_endian() -> None:
    # 0x00002041 LE = float 10.0 (DM4310 TMAX).
    assert decode(23, bytes.fromhex("00002041")).value == pytest.approx(10.0)
    # 0x20030000 LE = u32 800 (RID 9 timeout).
    assert decode(9, bytes.fromhex("20030000")).value == 800


def test_decode_tags_the_mandated_kind() -> None:
    tmax = decode(23, struct.pack("<f", 28.0))
    assert tmax.kind == "f32"
    assert tmax.name == "TMAX"
    timeout = decode(9, struct.pack("<I", 1000))
    assert timeout.kind == "u32"
    assert timeout.value == 1000


def test_decode_as_rejects_wrong_length() -> None:
    with pytest.raises(ValueError, match="4 bytes"):
        decode_as("u32", b"\x01\x02\x03")
