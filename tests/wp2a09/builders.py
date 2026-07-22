"""Self-contained builders for the WP-2A-09 preflight tests.

Everything a scenario needs is synthesised here from the reused primitives — a judged
RID read, a parsed CAN link state, a validated clamp canon — so the tests exercise the
real gate logic without a motor or a CAN device. Nothing here reaches into another WP's
owned fixtures; the byte layouts are packed locally so this tree owns all of its inputs.
"""

from __future__ import annotations

import struct

from backend.actuation import SafetyLimits
from backend.can.link import LinkState, parse_link_show
from backend.can.lock import LockState
from backend.can.rid.dump import MotorDump, RidDump
from backend.can.rid.evaluate import DumpEvaluation, evaluate_dump
from backend.can.rid.layout import ARM_SEND_IDS, expected_type
from backend.can.rid.motor_limits import MOTOR_LIMIT_PARAMS
from backend.can.rid.registers import RID_PMAX, RID_TIMEOUT, RID_TMAX, RID_VMAX
from backend.preflight import PreflightInputs, RidCrosscheck
from contracts.plugin.config import Side
from contracts.units import Deg, Nm

# RID 9 send-period margin (50 µs LSBs) the synthetic reads are judged against, matching
# the re-verification default so the offline and deferred paths judge identically.
MARGIN_LSB = 20
# A comm-loss timeout comfortably above the margin, so the synthetic RID 9 read is
# adequate and never itself the reason a gate blocks.
_TIMEOUT_LSB = 200

TEST_IFACE = "oa_fl"


def _f32(value: float) -> bytes:
    """Pack a float32 RID value in the little-endian layout the decoder reads."""
    return struct.pack("<f", value)


def _u32(value: int) -> bytes:
    """Pack a uint32 RID value in the little-endian layout the decoder reads."""
    return struct.pack("<I", value)


def build_rid_evaluation(
    *,
    iface: str = TEST_IFACE,
    break_motor: int | None = None,
    break_rid: int | None = None,
    break_value: float | None = None,
    drop_timeout_on: int | None = None,
) -> DumpEvaluation:
    """Judge a synthetic one-arm RID read, optionally corrupting one motor's register.

    Every motor is packed with its registered `MOTOR_LIMIT_PARAMS` value for RID
    21/22/23 and an adequate RID 9 timeout, so an unbroken build is a fully matching
    read. `break_*` replaces one register with a wrong value (a mismatch scenario);
    `drop_timeout_on` omits a motor's RID 9 (a partial read, `PG-RID-001`).

    Args:
        iface: Interface name recorded on the dump.
        break_motor: CAN id whose register to corrupt, or None for a clean read.
        break_rid: The RID (21/22/23) to corrupt on `break_motor`.
        break_value: The wrong value to write.
        drop_timeout_on: CAN id whose RID 9 to omit, or None to keep all.

    Returns:
        (DumpEvaluation) The judged read, ready to wrap as confirmed evidence.
    """
    motors: dict[int, MotorDump] = {}
    for motor_id in ARM_SEND_IDS:
        limit = MOTOR_LIMIT_PARAMS[expected_type(motor_id)]
        values = {RID_PMAX: limit.p_max, RID_VMAX: limit.v_max, RID_TMAX: limit.t_max}
        if motor_id == break_motor and break_rid is not None and break_value is not None:
            values[break_rid] = break_value
        registers = {rid: _f32(value) for rid, value in values.items()}
        if motor_id != drop_timeout_on:
            registers[RID_TIMEOUT] = _u32(_TIMEOUT_LSB)
        motors[motor_id] = MotorDump(
            motor_id=motor_id, expected_type=None, registers=registers, declared_kinds={}
        )
    return evaluate_dump(RidDump(iface=iface, motors=motors), MARGIN_LSB)


def capture_dict(
    *,
    iface: str = TEST_IFACE,
    break_motor: int | None = None,
    break_rid: int | None = None,
    break_value: float | None = None,
) -> dict[str, object]:
    """Build one interface's RID capture in the on-disk `dump.py` JSON schema.

    Mirrors `build_rid_evaluation` but emits the hex-per-register schema a real
    `openarm-can-cli show_param` capture uses, so the re-verification hook can be
    exercised end to end against a file — the same code path a real capture drives.

    Args:
        iface: Interface name recorded on the capture.
        break_motor: CAN id whose register to corrupt, or None for a clean capture.
        break_rid: The RID (21/22/23) to corrupt on `break_motor`.
        break_value: The wrong value to write.

    Returns:
        (dict[str, object]) The capture object, ready to `json.dump`.
    """
    motors: dict[str, object] = {}
    for motor_id in ARM_SEND_IDS:
        limit = MOTOR_LIMIT_PARAMS[expected_type(motor_id)]
        values = {RID_PMAX: limit.p_max, RID_VMAX: limit.v_max, RID_TMAX: limit.t_max}
        if motor_id == break_motor and break_rid is not None and break_value is not None:
            values[break_rid] = break_value
        registers = {str(rid): _f32(value).hex() for rid, value in values.items()}
        registers[str(RID_TIMEOUT)] = _u32(_TIMEOUT_LSB).hex()
        motors[f"0x{motor_id:02x}"] = {"registers": registers}
    return {"iface": iface, "motors": motors}


_LINK_FD_ON = """\
3: can0: <NOARP,UP,LOWER_UP> mtu 72 qdisc pfifo_fast state UP qlen 1000
    link/can  promiscuity 0 minmtu 0 maxmtu 0
    can <FD,TDC-AUTO> state ERROR-ACTIVE (berr-counter tx 0 rx 0) restart-ms 100
          bitrate 1000000 sample-point 0.750
          dbitrate 5000000 dsample-point 0.750
    clock 80000000 numtxqueues 1 numrxqueues 1
"""

_LINK_FD_OFF = """\
3: can0: <NOARP,UP,LOWER_UP> mtu 16 qdisc pfifo_fast state UP qlen 1000
    link/can  promiscuity 0 minmtu 0 maxmtu 0
    can state ERROR-ACTIVE (berr-counter tx 0 rx 0) restart-ms 0
          bitrate 1000000 sample-point 0.875
    clock 80000000 numtxqueues 1 numrxqueues 1
"""


def link_fd_on(iface: str = "can0") -> LinkState:
    """Parse a CAN-FD-on `ip -details link show` at the required rates."""
    return parse_link_show(_LINK_FD_ON, iface)


def link_fd_off(iface: str = "can0") -> LinkState:
    """Parse a CAN-2.0 (fd off) `ip -details link show` — the item ③ block case."""
    return parse_link_show(_LINK_FD_OFF, iface)


def _limits(width: int, *, mechanical_deg: float, operational_deg: float) -> SafetyLimits:
    """Build a uniform-per-joint limit set with loose, separate rate guards."""
    return SafetyLimits(
        mechanical_deg=tuple((Deg(-mechanical_deg), Deg(mechanical_deg)) for _ in range(width)),
        operational_deg=tuple((Deg(-operational_deg), Deg(operational_deg)) for _ in range(width)),
        velocity_limit_rad_s=tuple(1.0 for _ in range(width)),
        accel_limit_rad_s2=tuple(1.0 for _ in range(width)),
        jerk_limit_rad_s3=tuple(1.0 for _ in range(width)),
        step_delta_limit_rad=tuple(1.0 for _ in range(width)),
        peak_torque_nm=tuple(Nm(40.0) for _ in range(width)),
        operational_torque_nm=tuple(Nm(40.0) for _ in range(width)),
    )


def valid_clamp_canon(width: int = 2) -> SafetyLimits:
    """A canon whose operational envelope is a subset of mechanical — passes validate."""
    return _limits(width, mechanical_deg=180.0, operational_deg=90.0)


def invalid_clamp_canon(width: int = 2) -> SafetyLimits:
    """A canon whose operational envelope is wider than mechanical — validate rejects it."""
    return _limits(width, mechanical_deg=90.0, operational_deg=180.0)


def passing_inputs(lock_state: LockState) -> PreflightInputs:
    """Assemble a `PreflightInputs` in which all five preconditions pass.

    A single field is then overridden per test (via `dataclasses.replace`) so exactly
    one precondition fails, which is how each RUNS-HERE item shows it blocks in isolation.

    Args:
        lock_state: A writer-lock state this process holds (from the fixture).

    Returns:
        (PreflightInputs) Inputs whose preflight permits torque-ON.
    """
    return PreflightInputs(
        rid=RidCrosscheck.confirmed(build_rid_evaluation()),
        side=Side.LEFT,
        link=link_fd_on(),
        lock_state=lock_state,
        clamp_canon=valid_clamp_canon(),
    )
