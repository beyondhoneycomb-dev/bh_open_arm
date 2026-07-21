"""The RID-dump model: raw read-back bytes per motor, from synthetic or real captures.

A dump is the read-only artifact this WP produces — for each motor, the four
little-endian value bytes of each RID read (`03` §2.5). One schema serves both the
synthetic fixtures that run here and the real 16-motor capture that is deferred, so
that the re-verification hook (`reverify.py`) re-runs the identical decode and
judgment against real bytes the moment a capture is supplied (plan 02a §4.1).

The dump carries the register `Type` column that `openarm-can-cli show_param`
prints (`03` §2.6). That column is what makes the type-misread check meaningful on
real data: a recorded type that disagrees with the `03` FR-MOT-010 rule is a
detected misread, not a silent one.

JSON schema::

    {
      "iface": "oa_fl",
      "motors": {
        "0x07": {
          "expected_type": "DM4310",          # optional; else looked up by id
          "registers": {"23": "00002041"},    # rid -> 4-byte LE hex
          "declared_kinds": {"9": "f32"}       # optional; the tool's Type column
        }
      }
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.can.rid.decoder import RidKind, RidValue, decode, mandated_kind
from backend.can.rid.motor_limits import MotorType


def _parse_motor_id(raw: str) -> int:
    """Parse a motor-id key, accepting `0x07` hex or plain decimal.

    Args:
        raw: The key as written in the dump.

    Returns:
        (int) The CAN id.
    """
    return int(raw, 16) if raw.lower().startswith("0x") else int(raw, 10)


@dataclass(frozen=True)
class MotorDump:
    """One motor's RID read-backs.

    Attributes:
        motor_id: The CAN send id.
        expected_type: The registered motor type, when the dump pins it; else
            None and the caller looks it up from the layout.
        registers: RID -> the four little-endian value bytes read.
        declared_kinds: RID -> the type the capture recorded it under (the tool's
            `Type` column). Absent entries default to the mandated type.
    """

    motor_id: int
    expected_type: MotorType | None
    registers: dict[int, bytes]
    declared_kinds: dict[int, RidKind]

    def has(self, rid: int) -> bool:
        """Report whether this motor's dump carries a given RID.

        Args:
            rid: The register id.

        Returns:
            (bool) True when the RID was read for this motor.
        """
        return rid in self.registers

    def decoded(self, rid: int) -> RidValue:
        """Decode one RID under the `03` FR-MOT-010 mandated type.

        Args:
            rid: The register id.

        Returns:
            (RidValue) The decoded value.

        Raises:
            KeyError: If the RID was not read for this motor.
        """
        return decode(rid, self.registers[rid])

    def declared_kind(self, rid: int) -> RidKind:
        """Return the type the capture recorded a RID under.

        Args:
            rid: The register id.

        Returns:
            (RidKind) The recorded type, or the mandated type when the capture
            did not record one.
        """
        return self.declared_kinds.get(rid, mandated_kind(rid))

    def misread_entries(self) -> list[tuple[int, int, bytes, RidKind]]:
        """Yield `(motor_id, rid, raw, declared_kind)` for every read register.

        This is the input shape `decoder.find_type_misreads` consumes; feeding it
        every register lets the misread check compare each recorded type against
        the rule.

        Returns:
            (list) One tuple per read RID, in ascending RID order.
        """
        return [
            (self.motor_id, rid, self.registers[rid], self.declared_kind(rid))
            for rid in sorted(self.registers)
        ]


@dataclass(frozen=True)
class RidDump:
    """A full RID capture: every motor's read-backs on one interface.

    Attributes:
        iface: The CAN interface the dump was captured on.
        motors: CAN send id -> that motor's dump.
    """

    iface: str
    motors: dict[int, MotorDump]

    def motor_ids(self) -> tuple[int, ...]:
        """Return the motor ids present, in ascending order.

        Returns:
            (tuple[int, ...]) The CAN send ids in the dump.
        """
        return tuple(sorted(self.motors))

    def all_misread_entries(self) -> list[tuple[int, int, bytes, RidKind]]:
        """Collect the misread-check input across every motor in the dump.

        Returns:
            (list) `(motor_id, rid, raw, declared_kind)` for every read register.
        """
        entries: list[tuple[int, int, bytes, RidKind]] = []
        for motor_id in self.motor_ids():
            entries.extend(self.motors[motor_id].misread_entries())
        return entries


def parse_dump(data: dict[str, Any]) -> RidDump:
    """Build a `RidDump` from the parsed JSON schema.

    Args:
        data: The parsed dump object (`iface`, `motors`).

    Returns:
        (RidDump) The typed dump.

    Raises:
        ValueError: If a required field is missing or a hex value is malformed.
    """
    iface = data.get("iface")
    if not isinstance(iface, str):
        raise ValueError("dump is missing a string 'iface'")
    raw_motors = data.get("motors")
    if not isinstance(raw_motors, dict):
        raise ValueError("dump is missing a 'motors' object")

    motors: dict[int, MotorDump] = {}
    for id_key, body in raw_motors.items():
        motor_id = _parse_motor_id(str(id_key))
        registers = {
            int(rid): bytes.fromhex(str(hex_value))
            for rid, hex_value in dict(body.get("registers", {})).items()
        }
        declared = {
            int(rid): _as_kind(str(kind))
            for rid, kind in dict(body.get("declared_kinds", {})).items()
        }
        type_name = body.get("expected_type")
        expected = MotorType(type_name) if isinstance(type_name, str) else None
        motors[motor_id] = MotorDump(
            motor_id=motor_id,
            expected_type=expected,
            registers=registers,
            declared_kinds=declared,
        )
    return RidDump(iface=iface, motors=motors)


def _as_kind(raw: str) -> RidKind:
    """Coerce a recorded type string to a `RidKind`.

    Accepts the tool's spellings (`uint32`, `float32`) as well as the internal
    `u32`/`f32`, so a real `show_param` `Type` column parses directly.

    Args:
        raw: The recorded type token.

    Returns:
        (RidKind) `"u32"` or `"f32"`.

    Raises:
        ValueError: If the token is not a recognised type.
    """
    token = raw.strip().lower()
    if token in ("u32", "uint32"):
        return "u32"
    if token in ("f32", "float32", "float"):
        return "f32"
    raise ValueError(f"unrecognised RID type: {raw!r}")


def load_dump(path: Path) -> RidDump:
    """Load and parse a RID dump from a JSON file.

    Args:
        path: Path to the dump JSON.

    Returns:
        (RidDump) The typed dump.
    """
    return parse_dump(json.loads(path.read_text(encoding="utf-8")))
