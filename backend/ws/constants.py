"""Named parameters of the single-WebSocket server (`WP-3B-15`).

Every literal the dispatch logic depends on is named here rather than spelled at a call
site. Values with an owner elsewhere are imported, not restated: the session field name
is `CTR-WS@v2`'s (`contracts.ws.LEASE_SESSION_FIELD`), and every frame type, direction,
field list and authority rule is read from `contracts.ws.FRAME_TABLE` at the point of
use. Restating any of those here would fork a frozen contract this WP only consumes.

Two things this module *does* own, because no contract fixes them:

- The envelope key that carries the frame-type tag. `CTR-WS@v2` fixes the set of frame
  types and each one's fields; it does not fix the JSON key the tag travels under, so
  that key is a transport decision and it lives here.
- The close codes. `CTR-WS@v2` declares no server-to-client error frame, so a refusal
  cannot be answered inside the envelope without adding an eleventh frame type to a
  frozen contract. The refusal is therefore a WebSocket close, which is part of RFC 6455
  rather than part of the contract — visible to the client as `onclose(code, reason)`,
  and distinct per refusal so a client can tell them apart.
"""

from __future__ import annotations

from contracts.ws import LEASE_SESSION_FIELD

# The one realtime route. `CTR-WS@v2` D-2 permits exactly one realtime channel, so this
# is the only websocket path the backend mounts and a second one is a contract violation
# rather than a feature.
REALTIME_ROUTE = "/ws/realtime"

# Handshake query parameters. The role is asserted by the connecting client here and is
# whatever the host's authentication layer put in the URL; this module does not
# authenticate, it reads. A deployment that lets a browser pick its own role has an
# authentication defect, not a WS defect.
ROLE_QUERY_PARAM = "role"
# The session identifier reuses the contract's own field name so the handshake and the
# frame bodies cannot end up calling one thing two names.
SESSION_QUERY_PARAM = LEASE_SESSION_FIELD

# The envelope key carrying the `WsFrameType` tag, both inbound and outbound.
ENVELOPE_TYPE_FIELD = "type"

# Close codes, in RFC 6455's 4000-4999 private range. One per refusal: a client that
# cannot tell a bad role from a malformed frame cannot fix either.
WS_CLOSE_UNKNOWN_ROLE = 4400
WS_CLOSE_MISSING_SESSION = 4401
WS_CLOSE_MALFORMED_FRAME = 4402
WS_CLOSE_UNKNOWN_FRAME_TYPE = 4403
WS_CLOSE_UNAUTHORIZED_FRAME = 4404
WS_CLOSE_WRONG_DIRECTION = 4405
WS_CLOSE_REARM_NOT_ISSUED = 4406
WS_CLOSE_FORBIDDEN_ORIGIN = 4407

# The header the browser stamps the calling page's origin into. A WebSocket handshake is
# not covered by the same-origin policy — the browser sends it and lets the server decide
# — so this header is the only thing standing between a page on any host and this control
# channel (`FR-OPS-090`).
ORIGIN_HEADER = "origin"

# RFC 6455 §5.5.1 caps the close frame's payload at 125 bytes, two of which are the
# code. A reason over this is truncated rather than left to the transport, because a
# transport that refuses the whole frame turns a readable refusal into a bare drop.
WS_CLOSE_REASON_MAX_BYTES = 123

# Latch attribution for a GUI soft stop, carried in the `ops.cancel` `LatchReason` the
# same way `backend/commloss/constants.py`'s `WATCHDOG_GATE_PREFIX` attributes its own
# latches. An audit that cannot tell a browser stop from a comm-loss latch cannot say
# whether an operator stopped the arm or the link did.
GUI_STOP_GATE_PREFIX = "GUI_SOFT_STOP"
GUI_STOP_PREVIOUS_STATE = "LIVE"
GUI_STOP_NEW_STATE = "LATCHED"

__all__ = [
    "ENVELOPE_TYPE_FIELD",
    "GUI_STOP_GATE_PREFIX",
    "GUI_STOP_NEW_STATE",
    "GUI_STOP_PREVIOUS_STATE",
    "ORIGIN_HEADER",
    "REALTIME_ROUTE",
    "ROLE_QUERY_PARAM",
    "SESSION_QUERY_PARAM",
    "WS_CLOSE_FORBIDDEN_ORIGIN",
    "WS_CLOSE_MALFORMED_FRAME",
    "WS_CLOSE_MISSING_SESSION",
    "WS_CLOSE_REARM_NOT_ISSUED",
    "WS_CLOSE_REASON_MAX_BYTES",
    "WS_CLOSE_UNAUTHORIZED_FRAME",
    "WS_CLOSE_UNKNOWN_FRAME_TYPE",
    "WS_CLOSE_UNKNOWN_ROLE",
    "WS_CLOSE_WRONG_DIRECTION",
]
