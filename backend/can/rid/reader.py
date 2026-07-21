"""The read source the harness pulls RID values from — read-only, by construction.

The harness never opens a CAN socket itself; it asks a `RidReader` for the value
bytes. Two things follow from that shape. First, the only verb the interface has is
`read` — there is no write path to omit, the contract is read-only because the type
is (`03` FR-MOT-007 keeps raw CAN in `MOTOR_CONFIG` only, and this WP writes
nothing regardless). Second, the synthetic fixture reader and the real reader are
the same interface, so the synthetic acceptances here and the deferred real capture
run through identical harness code.

`FixtureRidReader` serves pre-captured dumps and is what runs on this host. The real
reader — a subprocess wrapper over `openarm-can-cli show_param` (read-only) against
16 powered motors — is deferred to the re-verification hook; it is described here,
not stubbed, so nothing pretends to reach hardware that is absent.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from backend.can.rid.dump import MotorDump, RidDump


class RidReader(Protocol):
    """A source of RID read-backs for an interface. Read-only: it only reads."""

    def read(self, iface: str, motor_ids: Sequence[int], rids: Sequence[int]) -> RidDump:
        """Read the given RIDs from the given motors on an interface.

        Args:
            iface: The CAN interface to read from.
            motor_ids: The motors to read.
            rids: The registers to read from each motor.

        Returns:
            (RidDump) The values that were read. A motor or RID that could not be
            read is simply absent — the caller's judgment treats absence as a read
            failure rather than inventing a value.
        """
        ...


class FixtureRidReader:
    """A `RidReader` that serves pre-captured dumps, one per interface.

    This is the read source on a host with no motors: it holds full captures and
    returns the requested motors/RIDs sliced out of them. A requested motor or RID
    that the capture does not contain is omitted, exactly as a real read failure
    would leave it.

    Args:
        captures: iface -> the full `RidDump` captured for that interface.
    """

    def __init__(self, captures: dict[str, RidDump]) -> None:
        self._captures = captures

    def read(self, iface: str, motor_ids: Sequence[int], rids: Sequence[int]) -> RidDump:
        """Slice the requested motors/RIDs out of the pre-captured dump.

        Args:
            iface: The interface whose capture to serve.
            motor_ids: The motors to include.
            rids: The registers to include per motor.

        Returns:
            (RidDump) The requested subset; absent motors/RIDs are omitted.

        Raises:
            KeyError: If no capture exists for `iface`.
        """
        source = self._captures[iface]
        wanted_rids = set(rids)
        motors: dict[int, MotorDump] = {}
        for motor_id in motor_ids:
            present = source.motors.get(motor_id)
            if present is None:
                continue
            registers = {rid: raw for rid, raw in present.registers.items() if rid in wanted_rids}
            declared = {
                rid: kind for rid, kind in present.declared_kinds.items() if rid in wanted_rids
            }
            motors[motor_id] = MotorDump(
                motor_id=motor_id,
                expected_type=present.expected_type,
                registers=registers,
                declared_kinds=declared,
            )
        return RidDump(iface=iface, motors=motors)
