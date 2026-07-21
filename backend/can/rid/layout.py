"""The registered per-arm motor layout the RID read-back is judged against.

`03` FR-MOT-001 registers each arm as eight motors with a fixed type per joint and
CAN send ids `0x01..0x08`. This module is that registration, so the harness knows
which `MOTOR_LIMIT_PARAMS` row each read-back *should* match. It is the registered
truth, deliberately separate from what the motors actually report — the whole
point of RID 21/22/23 (`03` FR-MOT-003) and RID 23 for J7 (`03` FR-MOT-004) is to
not trust this registration on documents alone but to check it against the motor.

Sixteen motors = two of these arms; a motor's identity in a dump is the pair
`(iface, motor_id)`, and the expected type is looked up by `motor_id` here.
"""

from __future__ import annotations

from backend.can.rid.motor_limits import MotorType

# Send CAN ids for one arm's eight motors (`03` FR-MOT-001, `openarm_cell.yaml`).
ARM_SEND_IDS: tuple[int, ...] = (0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08)

# Per-joint registered motor type, index 0 = J1 .. index 7 = J8 (`03` FR-MOT-001
# `types`). J3/J4 are DM4340; J5-J8 (including J7) are DM4310.
ARM_MOTOR_TYPES: tuple[MotorType, ...] = (
    MotorType.DM8009,
    MotorType.DM8009,
    MotorType.DM4340,
    MotorType.DM4340,
    MotorType.DM4310,
    MotorType.DM4310,
    MotorType.DM4310,
    MotorType.DM4310,
)

# J7 (wrist) is CAN id 0x07 and is registered DM4310 by four primary sources
# (`03` FR-MOT-004). RID 23 read-back of 5 Nm (DM3507) instead of 10 Nm is the
# mis-registration the boot guard exists to catch.
J7_MOTOR_ID = 0x07
J7_EXPECTED_TYPE = MotorType.DM4310

# The DM4340 joints (J3/J4) whose VMAX (RID 22) is judged 8 vs 10 vs 20 by
# `PG-VMAX-001` (`16` §3.1).
DM4340_MOTOR_IDS: tuple[int, ...] = (0x03, 0x04)

_TYPE_BY_ID = dict(zip(ARM_SEND_IDS, ARM_MOTOR_TYPES, strict=True))


def expected_type(motor_id: int) -> MotorType:
    """Return the registered motor type for a CAN send id within one arm.

    Args:
        motor_id: The CAN send id, `0x01..0x08`.

    Returns:
        (MotorType) The type `03` FR-MOT-001 registers at that id.

    Raises:
        KeyError: If `motor_id` is not one of the eight registered send ids.
    """
    return _TYPE_BY_ID[motor_id]
