"""What a host that reads the arm and does not command it owes a `command` frame.

`backend.actuation.ArmSession` holds the latch, the board and the lease for one process; it holds
no bus handle, so there is nowhere in it for a command frame to go. That is a property of the
deployment rather than of the frame, and the two must not be confused on the wire: the sender was
entitled to send, the frame was well formed, and the answer is still that nothing moved.

`CommandSink` was widened to carry exactly this — a sink that cannot route returns the close the
client is owed instead of returning None and reading as success. The close code is
`WS_CLOSE_COMMAND_UNROUTABLE` and deliberately not `WS_CLOSE_UNAUTHORIZED_FRAME`: an operator told
"unauthorised" goes looking for a permission they already hold.

The soft stop is unaffected and must stay so. It is not routed through here — the dispatcher
engages the shared latch itself — so a deployment with no send path still answers `FR-GUI-065`,
and the stop keeps working for the roles that hold no control authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.ws.constants import WS_CLOSE_COMMAND_UNROUTABLE
from backend.ws.dispatch import WsClosure
from backend.ws.session import WsSession

# What the operator reads in the close frame. It names what this process lacks rather than what
# was wrong with the frame, because nothing was.
READ_ONLY_HOST_REASON = "this process reads the arm and does not command it"


def refuse_command(session: WsSession, payload: Mapping[str, Any]) -> WsClosure:
    """Refuse one command frame visibly, naming the session and the fields it carried.

    Args:
        session: The connection the frame arrived on. Named in the reason so an operator with
            two tabs open can tell which of them was refused.
        payload: The frame's fields. Only their names are echoed — a control payload's values
            do not belong in a close reason a browser logs.

    Returns:
        (WsClosure) The close this client is owed.
    """
    return WsClosure(
        code=WS_CLOSE_COMMAND_UNROUTABLE,
        reason=f"{READ_ONLY_HOST_REASON}; {session.session_id} sent {sorted(payload)}",
    )


__all__ = ["READ_ONLY_HOST_REASON", "refuse_command"]
