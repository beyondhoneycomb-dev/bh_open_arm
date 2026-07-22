"""Jog-session torque-ON preflight (WP-2A-09).

Before a jog session may enable torque, five preconditions must each hold, and any
failure BLOCKS torque-ON — it is never downgraded to a warning (that downgrade is the
WP's named FAIL_BLOCKING negative branch). The five, and the Wave-0/Wave-1 primitive
each reuses rather than re-implements:

- ① RID 21/22/23 cross-check against `MOTOR_LIMIT_PARAMS` — reuses the `WP-0B-07` RID
  decoder/judgment (`backend.can.rid`). The *live* sixteen-motor read is hardware-
  deferred; its gate logic runs here on confirmed reads, and the deferral is fail-closed.
- ② `side` specified — reuses the `Side` contract (`contracts.plugin.config`).
- ③ CAN-FD link verified — reuses the `WP-0B-02` link verifier (`backend.can.link`).
- ④ writer lock held by this process — reuses the `WP-0B-01` lock (`backend.can.lock`),
  naming the holder PID on a foreign hold.
- ⑤ a valid canonical clamp limit set selected — reuses `SafetyLimits.validate`
  (`backend.actuation`).

The surface, in the order torque-ON flows through it: gather evidence into
`PreflightInputs`; `JogSessionPreflight.run` produces a `PreflightReport` whose
`may_enable_torque` is the conjunction of all five; `authorize_torque_on` raises
`TorqueOnBlockedError` unless every precondition passed. `reverify` is the hook the deferred
live RID cross-check re-runs against a real capture.

This layer opens no CAN socket, holds no lock, and sends no MIT frame: it is a pure
decision that the torque-ON path consults before it acts.
"""

from __future__ import annotations

from backend.preflight.checks import (
    check_can_fd,
    check_clamp_canon,
    check_rid_crosscheck,
    check_side,
    check_writer_lock,
)
from backend.preflight.gate import TorqueOnBlockedError, authorize_torque_on
from backend.preflight.model import CheckResult, PreflightCheck, RidCrosscheck
from backend.preflight.preflight import JogSessionPreflight, PreflightInputs, PreflightReport

__all__ = [
    "CheckResult",
    "JogSessionPreflight",
    "PreflightCheck",
    "PreflightInputs",
    "PreflightReport",
    "RidCrosscheck",
    "TorqueOnBlockedError",
    "authorize_torque_on",
    "check_can_fd",
    "check_clamp_canon",
    "check_rid_crosscheck",
    "check_side",
    "check_writer_lock",
]
