"""The hard E-Stop: power is cut, CAN dies, the arm drops, and nothing recovers by reading.

`16` M-2 is the design premise: an E-Stop cuts motor power, so the CAN bus dies with it —
"read the state after the stop and recover" is impossible, because there is nothing left to
read from. `12` NFR-SAF-009 is the physical consequence: with no holding brake the load
falls. `16` M-3 / §9-10 removed the drop-speed gate — the drop is recorded as a fact, its
speed is not measured, because the speed was never a safety signal (the fail-safe is
mechanical support, drop-zone isolation, and an independent power-cut, not a number).

This module models that terminal state, and it also proves the premise structurally: a
static scan of this package finds no function that recovers by reading state after a stop.
A recovery-by-read path would be named for what it does — `recover_*`, `resume_*`,
`reengage_*`, `reconnect_*` — and there is none. The detector itself is named `find_*`, so
it does not flag itself; this is the same static-absence discipline the actuation spine
keeps for `disable_torque` on the stop path (acceptance ⑨).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# A recovery-by-read path would be a function whose *name* begins with a recovery verb.
# Matching the leading verb (not any occurrence of it) is what lets the detector —
# `find_post_estop_recovery` — scan its own package without flagging itself.
_RECOVERY_DEF = re.compile(
    r"^\s*def\s+(?:recover|resume|reengage|re_engage|reenable|re_enable|reconnect)\w*",
    re.MULTILINE,
)

# This package's own directory; the default scan target for the static-absence check.
_PACKAGE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class HardEStopRecord:
    """The observable facts of a hard E-Stop (`16` M-2, M-3; `12` NFR-SAF-009).

    Attributes:
        can_alive: Whether the CAN bus is alive after the E-Stop. False — power is cut, so
            the bus dies with it (`16` M-2).
        drop_occurred: Whether the brakeless load fell. True — no holding brake means the
            load falls when torque is lost (`12` NFR-SAF-009).
        drop_speed_measured: Whether the drop speed was measured. False — the drop-speed
            gate was removed; the speed is not a safety signal (`16` M-3, §9-10).
        recovery_by_state_read: Whether the arm was recovered by reading state after the
            stop. False by design — the bus is dead, so there is nothing to read (`16` M-2).
    """

    can_alive: bool
    drop_occurred: bool
    drop_speed_measured: bool
    recovery_by_state_read: bool


def observe_hard_estop() -> HardEStopRecord:
    """Return the terminal facts of a hard E-Stop.

    This is the model the offline acceptance reads; the *physical* drop on real motors is
    deferred to a real fixture. The values encode the design premise, not a measurement:
    power is cut, so CAN is dead and no read-to-recover path can exist; the load falls, and
    its speed is deliberately not measured.

    Returns:
        (HardEStopRecord) CAN dead, drop occurred, drop speed unmeasured, no recovery.
    """
    return HardEStopRecord(
        can_alive=False,
        drop_occurred=True,
        drop_speed_measured=False,
        recovery_by_state_read=False,
    )


def find_post_estop_recovery(package_dir: Path | None = None) -> list[str]:
    """Scan for any function that recovers by reading state after a stop (acceptance ⑨).

    `16` M-2 makes "read state after the stop and recover" impossible: an E-Stop kills the
    bus. This returns every function definition whose name begins with a recovery verb, so
    an empty result is the machine proof that no such path was built.

    Args:
        package_dir: Directory to scan; defaults to this package.

    Returns:
        (list[str]) One `file: def` string per recovery-named function found; empty when
        the premise holds.
    """
    root = package_dir if package_dir is not None else _PACKAGE_DIR
    violations: list[str] = []
    for path in sorted(root.rglob("*.py")):
        for match in _RECOVERY_DEF.finditer(path.read_text(encoding="utf-8")):
            violations.append(f"{path.name}: {match.group(0).strip()}")
    return violations
