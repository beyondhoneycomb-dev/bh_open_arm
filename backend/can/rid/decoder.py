"""Decode a RID read-response payload, and detect a value read with the wrong type.

A Read Param response (`03` §2.5, `0x33`) carries the register value as four
little-endian data bytes. How those four bytes mean a number is decided solely by
the RID, per `03` FR-MOT-010: `registers.is_uint32_rid` says `uint32` or
`float32`. This module is that decode and its inverse concern — proving a value
was read under the *wrong* type (acceptance ⑦).

The type-misread check is the whole reason the harness is worth building before
hardware: a `uint32` timeout read as `float32` (or a `float32` TMAX read as
`uint32`) is silently plausible-looking garbage, and the only defence is to pin
the interpretation to the RID and flag any reading whose declared type disagrees.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Literal

from backend.can.rid.registers import is_uint32_rid, rid_name

# The two ways four little-endian bytes become a number under `03` FR-MOT-010.
RidKind = Literal["u32", "f32"]

RID_VALUE_BYTES = 4

_STRUCT_FORMAT: dict[RidKind, str] = {"u32": "<I", "f32": "<f"}


def mandated_kind(rid: int) -> RidKind:
    """Return the one type a RID's value must be decoded as (`03` FR-MOT-010).

    Args:
        rid: The register id.

    Returns:
        (RidKind) `"u32"` for RID 7-10/13-16/35-36, else `"f32"`.
    """
    return "u32" if is_uint32_rid(rid) else "f32"


def decode_as(kind: RidKind, raw: bytes) -> int | float:
    """Decode four little-endian bytes under an explicit type.

    This is the low-level primitive; callers that want the correct type for a RID
    use `decode`. It is exposed so the misread evidence can show what the *wrong*
    type would have produced from the same bytes.

    Args:
        kind: The interpretation to apply.
        raw: Exactly four bytes.

    Returns:
        (int | float) The decoded value.

    Raises:
        ValueError: If `raw` is not exactly four bytes.
    """
    if len(raw) != RID_VALUE_BYTES:
        raise ValueError(f"RID value must be {RID_VALUE_BYTES} bytes, got {len(raw)}")
    value = struct.unpack(_STRUCT_FORMAT[kind], raw)[0]
    # Pin the concrete type per kind: `struct.unpack` yields `Any`, and the two
    # formats yield an `int` (u32) and a `float` (f32) respectively.
    return int(value) if kind == "u32" else float(value)


@dataclass(frozen=True)
class RidValue:
    """A decoded RID value with the type it was decoded under.

    Attributes:
        rid: The register id.
        name: The `03` §2.6 register name (or a synthetic `RID_<n>`).
        kind: The type mandated by `03` FR-MOT-010 for this RID.
        raw: The four little-endian source bytes.
        value: The decoded number (`int` for u32, `float` for f32).
    """

    rid: int
    name: str
    kind: RidKind
    raw: bytes
    value: int | float


def decode(rid: int, raw: bytes) -> RidValue:
    """Decode a RID value under the type `03` FR-MOT-010 mandates for that RID.

    Args:
        rid: The register id, which alone decides the type.
        raw: The four little-endian value bytes from the read response.

    Returns:
        (RidValue) The decoded value tagged with its mandated type.
    """
    kind = mandated_kind(rid)
    return RidValue(rid=rid, name=rid_name(rid), kind=kind, raw=raw, value=decode_as(kind, raw))


@dataclass(frozen=True)
class TypeMisread:
    """A reading whose declared type disagrees with the RID's mandated type.

    Attributes:
        motor_id: The CAN id of the motor the value was read from.
        rid: The register id.
        declared_kind: The type the reading was recorded under.
        mandated_kind: The type `03` FR-MOT-010 requires for this RID.
        as_declared: The number the (wrong) declared type produces.
        as_mandated: The number the correct mandated type produces.
    """

    motor_id: int
    rid: int
    declared_kind: RidKind
    mandated_kind: RidKind
    as_declared: int | float
    as_mandated: int | float


def find_type_misreads(
    entries: list[tuple[int, int, bytes, RidKind]],
) -> list[TypeMisread]:
    """Flag readings whose declared type contradicts `03` FR-MOT-010.

    Each entry is `(motor_id, rid, raw, declared_kind)` — a value someone recorded
    together with the type they decoded it under. A misread is any entry whose
    `declared_kind` is not the RID's mandated kind; the finding carries both
    interpretations so the report can show the plausible-looking wrong number next
    to the correct one.

    Args:
        entries: Readings tagged with the type each was decoded under.

    Returns:
        (list[TypeMisread]) One finding per contradicting entry, sorted by
        `(motor_id, rid)`; empty when every declared type matches the rule.
    """
    misreads: list[TypeMisread] = []
    for motor_id, rid, raw, declared in entries:
        want = mandated_kind(rid)
        if declared == want:
            continue
        misreads.append(
            TypeMisread(
                motor_id=motor_id,
                rid=rid,
                declared_kind=declared,
                mandated_kind=want,
                as_declared=decode_as(declared, raw),
                as_mandated=decode_as(want, raw),
            )
        )
    return sorted(misreads, key=lambda item: (item.motor_id, item.rid))
