"""Damiao feedback ERR field -> OA-MOT-0xx, and the extraction upstream drops.

14 FR-OPS-018: the Damiao feedback frame carries an ERR nibble the hardware
already sends, but `MotorState` (`lerobot/motors/damiao/damiao.py`) is
`{position, velocity, torque, temp_mos, temp_rotor}` — no error field — so the
information is discarded. This module is the extraction that upstream never
performs, plus the 1:1 nibble<->code map (14 §2.4) read from the frozen registry.
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts.errors.constants import (
    DAMIAO_ENABLE_NIBBLE,
    DAMIAO_ERR_NIBBLE_MASK,
    DAMIAO_ERR_NIBBLE_SHIFT,
)
from contracts.errors.registry import REGISTRY, Registry


def nibble_to_code_map(registry: Registry) -> dict[str, str]:
    """Return the nibble->OA-MOT-code map declared in the frozen registry.

    Args:
        registry: The registry whose `damiao_err_nibble_map` to read.

    Returns:
        (dict[str, str]) Upper-hex nibble string to OA-MOT code.
    """
    mapping: dict[str, str] = {}
    for row in registry.nibble_map:
        if not isinstance(row, dict):
            continue
        nibble = str(row.get("nibble", "")).upper()
        code = str(row.get("code", ""))
        if nibble and code:
            mapping[nibble] = code
    return mapping


NIBBLE_TO_CODE = nibble_to_code_map(REGISTRY)


@dataclass(frozen=True)
class MotorErr:
    """The parsed motor error MotorState never exposes.

    Attributes:
        nibble: The raw ERR nibble as an upper-hex character.
        code: The OA-MOT code it maps to, or None for the Enable (normal) state.
        is_error: True when the nibble denotes a fault rather than a normal state.
    """

    nibble: str
    code: str | None
    is_error: bool


def extract_err_nibble(status_byte: int) -> str:
    """Extract the ERR nibble from a Damiao feedback status byte.

    This is the field `MotorState` drops: the high nibble of the status byte
    (`14` §2.4). Isolating it is the whole point — the same raw byte that upstream
    reduces to position/velocity/torque/temps carries this.

    Args:
        status_byte: The status byte from a Damiao feedback frame.

    Returns:
        (str) The ERR nibble as a single upper-hex character.
    """
    nibble = (status_byte >> DAMIAO_ERR_NIBBLE_SHIFT) & DAMIAO_ERR_NIBBLE_MASK
    return format(nibble, "X")


def parse_motor_err(status_byte: int) -> MotorErr:
    """Parse a Damiao status byte into a motor error, mapped to an OA-MOT code.

    Args:
        status_byte: The status byte from a Damiao feedback frame.

    Returns:
        (MotorErr) The nibble, its OA-MOT code (None for the Enable state), and
            whether it denotes a fault.
    """
    nibble = extract_err_nibble(status_byte)
    if int(nibble, 16) == DAMIAO_ENABLE_NIBBLE:
        return MotorErr(nibble=nibble, code=None, is_error=False)
    code = NIBBLE_TO_CODE.get(nibble)
    is_error = code is not None and code != "OA-MOT-000"
    return MotorErr(nibble=nibble, code=code, is_error=is_error)
