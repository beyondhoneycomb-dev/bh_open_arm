"""The DM feedback temperature decode reads D[6]=T_MOS (driver) and D[7]=T_Rotor (coil).

Spec 03 §2.7: the feedback frame's last two bytes are the two 1-byte temperatures. A
malformed frame is refused rather than read as a plausible low temperature that would
hide an over-temperature condition.
"""

from __future__ import annotations

import pytest

from backend.temp_gripper.constants import (
    COIL_TEMP_BYTE_INDEX,
    DRIVE_TEMP_BYTE_INDEX,
    FEEDBACK_FRAME_MIN_LEN,
)
from backend.temp_gripper.errors import TempGripperConfigError
from backend.temp_gripper.feedback import decode_motor_thermal


def test_drive_and_coil_come_from_bytes_6_and_7() -> None:
    frame = [0x08, 10, 20, 30, 40, 50, 118, 90]
    thermal = decode_motor_thermal(frame)
    assert thermal.drive_c == 118.0
    assert thermal.coil_c == 90.0


def test_byte_indices_are_the_last_two_of_the_frame() -> None:
    # The two temperature bytes are D[6] and D[7]; the decode must read exactly those.
    assert DRIVE_TEMP_BYTE_INDEX == 6
    assert COIL_TEMP_BYTE_INDEX == 7
    frame = [0] * FEEDBACK_FRAME_MIN_LEN
    frame[DRIVE_TEMP_BYTE_INDEX] = 77
    frame[COIL_TEMP_BYTE_INDEX] = 44
    thermal = decode_motor_thermal(frame)
    assert (thermal.drive_c, thermal.coil_c) == (77.0, 44.0)


def test_short_frame_is_refused() -> None:
    with pytest.raises(TempGripperConfigError, match="at least"):
        decode_motor_thermal([0, 0, 0, 0, 0, 0, 100])


def test_out_of_range_byte_is_refused() -> None:
    with pytest.raises(TempGripperConfigError, match="out of"):
        decode_motor_thermal([0, 0, 0, 0, 0, 0, 300, 90])


def test_zero_temperatures_decode() -> None:
    thermal = decode_motor_thermal([0] * 8)
    assert (thermal.drive_c, thermal.coil_c) == (0.0, 0.0)
