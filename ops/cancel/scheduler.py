"""Why a hold latch was applied, and when.

This is a type, not a contract. It was the argument of a `latch_to_hold` call that
`ops/cancel` made into the scheduler; that caller is gone and the call with it, but the
reason outlives both — the latch itself still needs a cause it can be audited by, and
the deadman controller, the WS dispatcher, the collision guard and the audit ring all
stamp one.

Release is deliberately absent, and that has not changed with the caller: clearing a
hold is an explicit re-arm handshake with a new generation id and operator intent, never
an automatic consequence of a condition later clearing itself.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LatchReason:
    """Why a hold latch was applied, and when.

    Fields match the P-0 evidence output of `05` §5.2: latch time plus `{gateId, previous state,
    new state}`. Carrying the gate identity matters because a latch with no attributable cause
    cannot be audited afterwards.
    """

    gate_id: str
    previous_state: str
    new_state: str
    latched_at: float
