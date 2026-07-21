"""Synthetic RID-dump builders for the WP-0B-07 tests.

These encode known motor read-backs into the `dump.py` JSON schema — the four
little-endian value bytes per RID — so the tests decode and judge real byte
patterns, not pre-decoded numbers. The same schema is what a real 16-motor capture
supplies to the re-verification hook, so a fixture built here and a capture built on
the rig flow through identical harness code.
"""

from __future__ import annotations

import struct
from typing import Any

from backend.can.rid.motor_limits import MOTOR_LIMIT_PARAMS, LimitParam, MotorType
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


def u32_hex(value: int) -> str:
    """Encode an unsigned 32-bit value as little-endian hex.

    Args:
        value: The unsigned integer.

    Returns:
        (str) Eight hex characters, little-endian.
    """
    return struct.pack("<I", value).hex()


def f32_hex(value: float) -> str:
    """Encode a 32-bit float as little-endian hex.

    Args:
        value: The float.

    Returns:
        (str) Eight hex characters, little-endian.
    """
    return struct.pack("<f", value).hex()


def limit_registers(limit: LimitParam) -> dict[str, str]:
    """Encode a `LimitParam` as the RID 21/22/23 read-back bytes.

    Args:
        limit: The PMAX/VMAX/TMAX values.

    Returns:
        (dict[str, str]) RID -> little-endian hex for 21, 22, 23.
    """
    return {
        str(RID_PMAX): f32_hex(limit.p_max),
        str(RID_VMAX): f32_hex(limit.v_max),
        str(RID_TMAX): f32_hex(limit.t_max),
    }


def protection_registers(uv: float, ot: float, oc: float, ov: float) -> dict[str, str]:
    """Encode UV/OT/OC/OV protection thresholds as read-back bytes (float32).

    Args:
        uv: Under-voltage threshold.
        ot: Over-temperature threshold.
        oc: Over-current threshold.
        ov: Over-voltage threshold.

    Returns:
        (dict[str, str]) RID -> little-endian hex for RID 0/2/3/29.
    """
    return {
        str(RID_UV): f32_hex(uv),
        str(RID_OT): f32_hex(ot),
        str(RID_OC): f32_hex(oc),
        str(RID_OV): f32_hex(ov),
    }


def healthy_motor(
    motor_type: MotorType,
    timeout_lsb: int,
) -> dict[str, Any]:
    """Build one motor's dump body with correct limits, timeout and protections.

    Args:
        motor_type: The motor type whose `MOTOR_LIMIT_PARAMS` the read-back matches.
        timeout_lsb: The RID 9 timeout in 50 us LSBs.

    Returns:
        (dict) A `motors[...]` body: registers for RID 9/21/22/23 and 0/2/3/29.
    """
    registers: dict[str, str] = {str(RID_TIMEOUT): u32_hex(timeout_lsb)}
    registers.update(limit_registers(MOTOR_LIMIT_PARAMS[motor_type]))
    registers.update(protection_registers(uv=18.0, ot=80.0, oc=20.0, ov=60.0))
    return {"expected_type": motor_type.value, "registers": registers}


def motor_with_limits(expected_type: MotorType, actual: LimitParam) -> dict[str, Any]:
    """Build a motor registered as one type but reporting another's limits.

    Args:
        expected_type: The type the arm registration expects.
        actual: The PMAX/VMAX/TMAX the motor actually reports.

    Returns:
        (dict) A `motors[...]` body whose RID 21/22/23 encode `actual`.
    """
    return {"expected_type": expected_type.value, "registers": limit_registers(actual)}


def dump(iface: str, motors: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """Assemble a full dump object from per-motor bodies.

    Args:
        iface: The CAN interface name.
        motors: motor_id -> the motor's dump body.

    Returns:
        (dict) The dump in the `dump.py` JSON schema.
    """
    return {"iface": iface, "motors": {f"0x{mid:02X}": body for mid, body in motors.items()}}
