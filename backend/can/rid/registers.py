"""The RID register map and the single type-interpretation rule for RID values.

`03` FR-MOT-010 fixes one rule for parsing every RID value read off a Damiao
motor: RID 7-10, 13-16 and 35-36 are `uint32`, everything else is `float32`, and
both are little-endian. The source of truth is `openarm_can`'s
`CanPacketDecoder::is_in_ranges()` (`dm_motor_control.cpp`); this module is that
predicate and the RID name table (`03` §2.6, FR-MOT-009) and nothing else. It
holds no decode logic — `decoder.py` owns that — so the type rule lives in exactly
one place and the whole harness reads it from here.

The named RID constants below are the registers this WP judges: the protection
thresholds (`03` FR-MOT-039), the comm-loss timeout (`16` M-4), and the scale
limits (`03` FR-MOT-003) that carry PMAX/VMAX/TMAX.
"""

from __future__ import annotations

# `03` FR-MOT-010 / `CanPacketDecoder::is_in_ranges`: the RID numbers whose value
# is a `uint32`. Every RID outside these closed ranges is a `float32`. The ranges
# are inclusive on both ends, exactly as the C++ predicate writes them.
UINT32_RID_RANGES: tuple[tuple[int, int], ...] = ((7, 10), (13, 16), (35, 36))

# Protection-threshold registers (`03` FR-MOT-039). All four fall outside the
# uint32 ranges, so they decode as float32.
RID_UV = 0  # Under-voltage protection threshold.
RID_OT = 2  # Over-temperature protection threshold.
RID_OC = 3  # Over-current protection threshold (= current limit).
RID_OV = 29  # Over-voltage protection threshold.

# Comm-loss timeout (`16` M-4): a uint32 in units of 50 us. On comm loss the motor
# fails safe by dropping enable, so the Cat-2 hold send period must stay under it
# (`12` NFR-SAF-007). RID 9 is inside 7-10, so it is uint32.
RID_TIMEOUT = 9
TIMEOUT_LSB_MICROSECONDS = 50

# Scale-limit registers (`03` FR-MOT-003): the motor's internally stored PMAX/
# VMAX/TMAX, compared against `MOTOR_LIMIT_PARAMS`. All three are float32.
RID_PMAX = 21
RID_VMAX = 22
RID_TMAX = 23

# Serial number (`03` §2.6): uint32, inside 13-16. Used by `04` FR-MAN-003 side
# cross-check; recorded but not judged by this WP.
RID_SN = 15

# The RID name table (`03` §2.6), used for the FR-MOT-009 five-column display. Not
# exhaustive of the 80+ registers — it names the ones this WP reads and reports.
RID_NAMES: dict[int, str] = {
    RID_UV: "UV_Value",
    1: "KT_Value",
    RID_OT: "OT_Value",
    RID_OC: "OC_Value",
    4: "ACC",
    5: "DEC",
    6: "MAX_SPD",
    7: "MST_ID",
    8: "ESC_ID",
    RID_TIMEOUT: "TIMEOUT",
    10: "CTRL_MODE",
    11: "Damp",
    12: "Inertia",
    13: "hw_ver",
    14: "sw_ver",
    RID_SN: "SN",
    16: "NPP",
    20: "Gr",
    RID_PMAX: "PMAX",
    RID_VMAX: "VMAX",
    RID_TMAX: "TMAX",
    RID_OV: "OV_Value",
    35: "can_br",
    36: "sub_ver",
}


def is_uint32_rid(rid: int) -> bool:
    """Report whether a RID's value is a `uint32` under `03` FR-MOT-010.

    Args:
        rid: The register id.

    Returns:
        (bool) True when `rid` is in 7-10, 13-16 or 35-36 (uint32); False means
        the value is a float32.
    """
    return any(low <= rid <= high for low, high in UINT32_RID_RANGES)


def rid_name(rid: int) -> str:
    """Return the register name for a RID, or a synthetic name when unlisted.

    Args:
        rid: The register id.

    Returns:
        (str) The `03` §2.6 name, or `RID_<n>` for a register this WP does not
        name (the value still decodes; only the display label is generic).
    """
    return RID_NAMES.get(rid, f"RID_{rid}")
