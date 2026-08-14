"""WP-3B-15 — the single-WebSocket server behind `CTR-WS@v2`.

This package is transport. Every decision it carries is made somewhere else, and the
list of what it delegates is the whole design:

- **Frame authority.** `contracts.ws.authorize_send` decides who may send what, off the
  frozen `FRAME_TABLE`. This package calls it and adds no second rule — which is why the
  soft stop reaches the latch from an observer: `STOP_HOLD` is marked
  `is_control_frame=False` in the contract, not exempted by a branch here.
- **The lease.** `backend.deadman.DeadmanController` judges every renewal, owns expiry on
  the server clock, and owns the re-arm handshake. This package rebuilds wire fields into
  the canon's own `LeaseRenewal` — which has no expiry field — and carries the verdict
  back. There is no second lease.
- **The latch.** `backend.actuation.latch.SafetyLatch`, reached through the
  `backend.deadman.LatchTarget` surface the deadman already drives. A GUI stop engages
  the same latch a deadman expiry does, so the arm has one held state. There is no
  second latch.
- **Roles.** `contracts.ws.WsRole`. There is no second role model.

What it owns: the envelope key the frame tag travels under, the close codes a refusal is
delivered with, the `PreviewSink` implementation over a real socket, and the route.

What it cannot do, stated so nobody reads the absence as an oversight:

- **It sends no telemetry and no camera frames.** Both are server-to-client classes with
  producers this WP does not own, so the route carries them the moment something is wired
  to `WsSession.preview_sink`, and carries nothing before that.
- **It does not acknowledge a soft stop.** `CTR-WS@v2` defines no server-to-client frame
  for it; the client learns the hold engaged through telemetry.
- **It authenticates nobody.** The role arrives on the handshake URL. Deciding *which*
  role a connection is entitled to belongs to the host's authentication layer, and a
  deployment that lets a browser choose has an authentication defect this package cannot
  see.
"""

from __future__ import annotations

from backend.ws.app import (
    handshake_session,
    mount_realtime_channel,
    truncate_close_reason,
)
from backend.ws.constants import (
    ENVELOPE_TYPE_FIELD,
    GUI_STOP_GATE_PREFIX,
    ORIGIN_HEADER,
    REALTIME_ROUTE,
    ROLE_QUERY_PARAM,
    SESSION_QUERY_PARAM,
    WS_CLOSE_COMMAND_UNROUTABLE,
    WS_CLOSE_FORBIDDEN_ORIGIN,
    WS_CLOSE_MALFORMED_FRAME,
    WS_CLOSE_MISSING_SESSION,
    WS_CLOSE_REARM_NOT_ISSUED,
    WS_CLOSE_UNAUTHORIZED_FRAME,
    WS_CLOSE_UNKNOWN_FRAME_TYPE,
    WS_CLOSE_UNKNOWN_ROLE,
    WS_CLOSE_WRONG_DIRECTION,
)
from backend.ws.deployment import (
    ControlChannelDeployment,
    DeploymentError,
    LoopbackDeployment,
    admitted_origins,
)
from backend.ws.dispatch import (
    CommandSink,
    DispatchOutcome,
    FrameDispatcher,
    WsClosure,
)
from backend.ws.session import WsSession
from backend.ws.sink import BinarySender, WebSocketPreviewSink

__all__ = [
    "ENVELOPE_TYPE_FIELD",
    "GUI_STOP_GATE_PREFIX",
    "REALTIME_ROUTE",
    "ROLE_QUERY_PARAM",
    "SESSION_QUERY_PARAM",
    "WS_CLOSE_COMMAND_UNROUTABLE",
    "WS_CLOSE_MALFORMED_FRAME",
    "WS_CLOSE_MISSING_SESSION",
    "ORIGIN_HEADER",
    "WS_CLOSE_FORBIDDEN_ORIGIN",
    "WS_CLOSE_REARM_NOT_ISSUED",
    "WS_CLOSE_UNAUTHORIZED_FRAME",
    "WS_CLOSE_UNKNOWN_FRAME_TYPE",
    "WS_CLOSE_UNKNOWN_ROLE",
    "WS_CLOSE_WRONG_DIRECTION",
    "BinarySender",
    "CommandSink",
    "ControlChannelDeployment",
    "DeploymentError",
    "DispatchOutcome",
    "FrameDispatcher",
    "LoopbackDeployment",
    "WebSocketPreviewSink",
    "WsClosure",
    "WsSession",
    "admitted_origins",
    "handshake_session",
    "mount_realtime_channel",
    "truncate_close_reason",
]
