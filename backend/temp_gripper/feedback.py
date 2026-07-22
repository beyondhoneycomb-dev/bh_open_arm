"""Decode the two temperatures the Damiao MIT feedback frame carries.

`openarm_can`'s `parse_motor_state_data()` reads D[1]..D[7] for position, velocity,
torque and the two temperatures but discards D[0] (the ERR nibble, decoded elsewhere
by `backend.actuation.errdecode` and consumed by `backend.commloss`). This module owns
only the two temperature bytes — D[6] = T_MOS (driver) and D[7] = T_Rotor (coil) — and
re-decodes nothing the ERR path owns.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.temp_gripper.constants import (
    COIL_CHANNEL,
    COIL_TEMP_BYTE_INDEX,
    DRIVE_CHANNEL,
    DRIVE_TEMP_BYTE_INDEX,
    FEEDBACK_FRAME_MIN_LEN,
    TEMP_BYTE_MAX,
    TEMP_BYTE_MIN,
)
from backend.temp_gripper.errors import TempGripperConfigError


@dataclass(frozen=True)
class MotorThermal:
    """One motor's two reported temperatures, °C.

    Attributes:
        drive_c: T_MOS, the driver MOSFET temperature (feedback D[6]).
        coil_c: T_Rotor, the motor coil temperature (feedback D[7]).
    """

    drive_c: float
    coil_c: float


def decode_motor_thermal(frame: Sequence[int]) -> MotorThermal:
    """Decode one motor's driver and coil temperatures from its feedback frame.

    Args:
        frame: The Damiao feedback frame's data bytes; at least `FEEDBACK_FRAME_MIN_LEN`
            unsigned bytes.

    Returns:
        (MotorThermal) The driver (D[6]) and coil (D[7]) temperatures, °C.

    Raises:
        TempGripperConfigError: If the frame is short or a temperature byte is not an
            unsigned byte — a malformed frame is refused rather than read as a plausible
            low temperature that would hide an over-temperature condition.
    """
    if len(frame) < FEEDBACK_FRAME_MIN_LEN:
        raise TempGripperConfigError(
            f"feedback frame needs at least {FEEDBACK_FRAME_MIN_LEN} bytes, got {len(frame)}"
        )
    readings = (
        (DRIVE_CHANNEL, frame[DRIVE_TEMP_BYTE_INDEX]),
        (COIL_CHANNEL, frame[COIL_TEMP_BYTE_INDEX]),
    )
    for name, value in readings:
        if not TEMP_BYTE_MIN <= value <= TEMP_BYTE_MAX:
            raise TempGripperConfigError(
                f"{name} temperature byte out of [{TEMP_BYTE_MIN}, {TEMP_BYTE_MAX}]: {value}"
            )
    return MotorThermal(
        drive_c=float(frame[DRIVE_TEMP_BYTE_INDEX]),
        coil_c=float(frame[COIL_TEMP_BYTE_INDEX]),
    )
