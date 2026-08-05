"""The inbound frame dispatcher: decode, authorize, route (`WP-3B-15`).

Data-in, decision-out, and it holds no socket. `dispatch` takes the raw text of one
inbound frame and returns either a reply envelope, a closure, or neither; the connection
handler is what writes to the wire. That split is what lets every routing rule be driven
by a test that opens no socket, and it is the same shape `backend.actuation.safety` uses
for the enforcement filter.

The check order is fixed, and each step exists because the one before it cannot answer
its question:

1. **Decode.** A frame that is not a JSON object with a string tag names nothing.
2. **Known type.** `WsFrameType(tag)` or the client named a frame this contract has no
   row for.
3. **Direction.** `FRAME_TABLE[frame].direction` must be client-to-server. This is
   before the authority check on purpose: `telemetry` and `camera` are not control
   frames, so `authorize_send` passes them for every role — a client pushing telemetry
   at the server would sail through an authority-first order.
4. **Authority.** `contracts.ws.authorize_send(role, frame)`, called for *every* frame
   including the soft stop, before any routing. `CG-G-01g` is explicit that hiding a
   control in the browser is not a refusal; this is the refusal. The stop passes because
   `FRAME_TABLE` marks it `is_control_frame=False`, not because of a branch here — a
   second exception written into this module is how the one rule becomes two.
5. **Route.**

What a refused client sees, in every case: the socket closes with a code from
`backend.ws.constants` and a reason naming what was refused and why. `CTR-WS@v2` declares
no server-to-client error frame, so there is no envelope a refusal could travel in;
adding one would put an eleventh frame type in a frozen contract. A close is visible to
the browser as `onclose(code, reason)` and cannot be mistaken for the frame having been
accepted, which is the property that matters. What it costs is stated where the cost
falls: an authority refusal drops a connection that could have kept streaming telemetry,
so a client that reaches this state must reconnect.

This module engages the latch and drives the deadman; it owns neither. Both arrive as
constructor arguments, and the host is expected to pass the *same* `LatchTarget` it gave
the `DeadmanController`, so a GUI stop and a deadman expiry land on one latch.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from backend.actuation.clock import Clock
from backend.deadman import (
    DeadmanController,
    LatchTarget,
    LeaseRenewal,
    RearmError,
    RenewalResult,
)
from backend.ws.constants import (
    ENVELOPE_TYPE_FIELD,
    GUI_STOP_GATE_PREFIX,
    GUI_STOP_NEW_STATE,
    GUI_STOP_PREVIOUS_STATE,
    WS_CLOSE_MALFORMED_FRAME,
    WS_CLOSE_REARM_NOT_ISSUED,
    WS_CLOSE_UNAUTHORIZED_FRAME,
    WS_CLOSE_UNKNOWN_FRAME_TYPE,
    WS_CLOSE_WRONG_DIRECTION,
)
from backend.ws.session import WsSession
from contracts.prim import LEASE_EXPIRY_FIELD, LEASE_ISSUED_FIELD
from contracts.ws import (
    FRAME_TABLE,
    LEASE_GENERATION_FIELD,
    LEASE_REASON_FIELD,
    LEASE_SEQUENCE_FIELD,
    LEASE_SESSION_FIELD,
    FrameDirection,
    LeaseRejectReason,
    WsError,
    WsFrameType,
    authorize_send,
)
from ops.cancel.scheduler import LatchReason

# What the dispatcher hands a well-formed, authorised `command` frame to. Required, not
# optional: a default would let a server that consumes no command be indistinguishable
# from one that does, and an operator would watch their command leave and nothing move.
CommandSink = Callable[[WsSession, Mapping[str, Any]], None]


@dataclass(frozen=True)
class WsClosure:
    """The close the server owes a client whose frame it refused.

    Attributes:
        code: The `backend.ws.constants` close code naming which refusal this is.
        reason: The human-readable cause, truncated by the connection handler to the
            RFC 6455 close-payload limit.
    """

    code: int
    reason: str


@dataclass(frozen=True)
class DispatchOutcome:
    """What the connection handler must do after one inbound frame.

    The two fields are independent rather than a union: a routed frame produces a reply
    and no closure, a refusal produces a closure and no reply, and an accepted frame with
    no contract-defined answer (the soft stop) produces neither. Collapsing them would
    make "handled, nothing to say" indistinguishable from "not handled".

    Attributes:
        reply: The envelope to send back, or None when the contract defines no answer.
        closure: The close to perform, or None when the connection continues.
    """

    reply: dict[str, Any] | None = None
    closure: WsClosure | None = None


class FrameDispatcher:
    """Routes one client's inbound frames onto the shared lease and the shared latch.

    Ownership: holds the arm's `LatchTarget` and `DeadmanController` (neither owned — the
    host owns both and is expected to have built them over one latch), a clock for latch
    timestamps, and the host's command sink. It holds no socket, no lease of its own and
    no latch of its own.
    """

    def __init__(
        self,
        latch_target: LatchTarget,
        deadman: DeadmanController,
        clock: Clock,
        command_sink: CommandSink,
    ) -> None:
        """Wire the dispatcher to the shared safety state and the host's command sink.

        Args:
            latch_target: The arm's latch surface — the same one the `DeadmanController`
                drives, so a GUI stop and a deadman expiry engage one latch.
            deadman: The lease canon (`WP-2A-02`). Renewal, expiry and the re-arm
                handshake are decided there and only transported here.
            clock: The server monotonic clock the latch timestamp is stamped from. The
                same clock the deadman judges expiry on, so an audit can order a stop
                against an expiry.
            command_sink: Where an authorised command goes.
        """
        self._latch_target = latch_target
        self._deadman = deadman
        self._clock = clock
        self._command_sink = command_sink

    def dispatch(self, session: WsSession, raw: str) -> DispatchOutcome:
        """Decode, authorise and route one inbound text frame.

        Args:
            session: The connection this frame arrived on.
            raw: The frame's raw text.

        Returns:
            (DispatchOutcome) The reply to send, the close to perform, or neither.
        """
        decoded = _decode(raw)
        if isinstance(decoded, WsClosure):
            return DispatchOutcome(closure=decoded)

        frame_type, payload = decoded
        spec = FRAME_TABLE[frame_type]
        if spec.direction is not FrameDirection.CLIENT_TO_SERVER:
            return DispatchOutcome(
                closure=WsClosure(
                    code=WS_CLOSE_WRONG_DIRECTION,
                    reason=(
                        f"{frame_type.value!r} is a {spec.direction.value} frame; "
                        "a client may not send it"
                    ),
                )
            )

        try:
            authorize_send(session.role, frame_type)
        except WsError as refused:
            return DispatchOutcome(
                closure=WsClosure(code=WS_CLOSE_UNAUTHORIZED_FRAME, reason=str(refused))
            )

        return self._route(session, frame_type, payload)

    def _route(
        self, session: WsSession, frame_type: WsFrameType, payload: Mapping[str, Any]
    ) -> DispatchOutcome:
        """Dispatch an authorised frame to its handler.

        A total map over the client-to-server frames: every one the direction check
        admitted has a branch, so a frame type added to `CTR-WS@v2` fails this method
        rather than being dropped by a fall-through that looks like success.
        """
        if frame_type is WsFrameType.STOP_HOLD:
            return self._stop_hold(session)
        if frame_type is WsFrameType.LEASE_RENEW:
            return self._lease_renew(session, payload)
        if frame_type is WsFrameType.REARM_CONFIRM:
            return self._rearm_confirm(session)
        if frame_type is WsFrameType.COMMAND:
            self._command_sink(session, payload)
            return DispatchOutcome()
        raise WsError(f"no route for client frame {frame_type.value!r}")

    def _stop_hold(self, session: WsSession) -> DispatchOutcome:
        """Engage the shared safety latch, attributed to this GUI session.

        Engaged unconditionally rather than after reading `latch_active`: `SafetyLatch`
        already keeps the first reason on a re-engage, so idempotency is the latch's
        property and a read-then-engage here would only add a window in which two stops
        race to decide which of them is the "first".

        The reason is server-authored end to end — this surface's gate id, this server's
        clock. The frame carries a session id and nothing else, because a client-supplied
        cause or time on a safety path is a forgeable audit.

        Returns:
            (DispatchOutcome) Neither reply nor closure. `CTR-WS@v2` defines no
            server-to-client acknowledgement for the stop, so there is no frame to answer
            in; the client observes the hold through telemetry.
        """
        self._latch_target.engage_safety_latch(
            LatchReason(
                gate_id=f"{GUI_STOP_GATE_PREFIX}:{session.session_id}",
                previous_state=GUI_STOP_PREVIOUS_STATE,
                new_state=GUI_STOP_NEW_STATE,
                latched_at=self._clock.now(),
            )
        )
        return DispatchOutcome()

    def _lease_renew(self, session: WsSession, payload: Mapping[str, Any]) -> DispatchOutcome:
        """Transport one renewal to the deadman and carry its verdict back.

        The renewal is rebuilt into the canon's own `LeaseRenewal`, which has no expiry
        field, so nothing a client sent can reach an expiry decision.
        """
        renewal = _renewal_from(payload)
        if isinstance(renewal, WsClosure):
            return DispatchOutcome(closure=renewal)
        result = self._deadman.receive_renewal(renewal)
        return DispatchOutcome(reply=_lease_reply(session, renewal, result))

    def _rearm_confirm(self, session: WsSession) -> DispatchOutcome:
        """Confirm the operator half of the re-arm handshake and report the generation.

        The three lease-record fields on `rearm_accept` are null here, and that is the
        honest answer rather than a gap: `confirm_rearm` arms a generation and clears the
        latch, it does not grant a lease. No renewal has been accepted under the new
        generation yet, so the server has computed no expiry — and stating one would be
        this surface authoring an expiry the deadman never decided, which is the single
        thing `CTR-WS@v2`'s clock ownership exists to prevent. The client sends a
        `lease_renew` next, and that reply carries the real expiry.
        """
        try:
            generation = self._deadman.confirm_rearm()
        except RearmError as refused:
            return DispatchOutcome(
                closure=WsClosure(code=WS_CLOSE_REARM_NOT_ISSUED, reason=str(refused))
            )
        return DispatchOutcome(
            reply=_envelope(
                WsFrameType.REARM_ACCEPT,
                {
                    LEASE_SESSION_FIELD: session.session_id,
                    LEASE_GENERATION_FIELD: generation,
                    LEASE_EXPIRY_FIELD: None,
                    LEASE_SEQUENCE_FIELD: None,
                    LEASE_ISSUED_FIELD: None,
                },
            )
        )


def _decode(raw: str) -> tuple[WsFrameType, Mapping[str, Any]] | WsClosure:
    """Turn raw frame text into a frame type and its payload, or the closure it earns.

    Args:
        raw: The inbound frame's text.

    Returns:
        (tuple[WsFrameType, Mapping[str, Any]] | WsClosure) The decoded frame, or the
        close to perform.
    """
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as broken:
        return WsClosure(code=WS_CLOSE_MALFORMED_FRAME, reason=f"frame is not JSON: {broken.msg}")
    if not isinstance(payload, dict):
        return WsClosure(
            code=WS_CLOSE_MALFORMED_FRAME,
            reason=f"frame must be a JSON object carrying {ENVELOPE_TYPE_FIELD!r}",
        )
    tag = payload.get(ENVELOPE_TYPE_FIELD)
    if not isinstance(tag, str):
        return WsClosure(
            code=WS_CLOSE_MALFORMED_FRAME,
            reason=f"frame carries no string {ENVELOPE_TYPE_FIELD!r} tag",
        )
    try:
        frame_type = WsFrameType(tag)
    except ValueError:
        return WsClosure(
            code=WS_CLOSE_UNKNOWN_FRAME_TYPE,
            reason=f"unknown frame type {tag!r}; this channel carries "
            f"{', '.join(sorted(frame.value for frame in WsFrameType))}",
        )
    return frame_type, payload


def _renewal_from(payload: Mapping[str, Any]) -> LeaseRenewal | WsClosure:
    """Build the canon renewal from the wire fields, or the closure a bad one earns.

    A missing or mistyped lease field is a broken client, not a lease decision: answering
    it with a `lease_reject` would spend one of the canon's six distinct refusal reasons
    on a cause none of them means, and the audit would then read a malformed frame as a
    replay or a stale generation.
    """
    generation = payload.get(LEASE_GENERATION_FIELD)
    sequence = payload.get(LEASE_SEQUENCE_FIELD)
    issued = payload.get(LEASE_ISSUED_FIELD)
    # `bool` is an `int` subclass, so it is excluded explicitly: `True` as a generation
    # would otherwise be accepted and compared as 1.
    if (
        not isinstance(generation, int)
        or isinstance(generation, bool)
        or not isinstance(sequence, int)
        or isinstance(sequence, bool)
        or not isinstance(issued, int | float)
        or isinstance(issued, bool)
    ):
        return WsClosure(
            code=WS_CLOSE_MALFORMED_FRAME,
            reason=(
                f"{WsFrameType.LEASE_RENEW.value!r} needs integer "
                f"{LEASE_GENERATION_FIELD!r} and {LEASE_SEQUENCE_FIELD!r} and a numeric "
                f"{LEASE_ISSUED_FIELD!r}"
            ),
        )
    return LeaseRenewal(
        generation=generation,
        sequence=sequence,
        issued_mono_client=float(issued),
    )


def _lease_reply(
    session: WsSession, renewal: LeaseRenewal, result: RenewalResult
) -> dict[str, Any]:
    """Render the deadman's verdict as the grant or reject frame that carries it.

    The reject reason is looked up by value rather than mapped through a table here:
    `LeaseRejectReason`'s members are exactly the non-accepted `RenewalDecision` members
    by value, which `tests/wp3a04/test_lease_transport.py:68` asserts. A `ValueError` out
    of that lookup means the two trees have drifted, and it is left to raise — a
    substituted reason would tell the audit a replay was an aged message.
    """
    if result.accepted and result.lease is not None:
        lease = result.lease
        return _envelope(
            WsFrameType.LEASE_GRANT,
            {
                LEASE_SESSION_FIELD: session.session_id,
                LEASE_GENERATION_FIELD: lease.generation,
                LEASE_EXPIRY_FIELD: lease.expiry_mono_server,
                LEASE_SEQUENCE_FIELD: lease.sequence,
                LEASE_ISSUED_FIELD: lease.issued_mono_client,
            },
        )
    return _envelope(
        WsFrameType.LEASE_REJECT,
        {
            LEASE_SESSION_FIELD: session.session_id,
            LEASE_GENERATION_FIELD: renewal.generation,
            LEASE_REASON_FIELD: LeaseRejectReason(result.decision.value).value,
        },
    )


def _envelope(frame_type: WsFrameType, body: dict[str, Any]) -> dict[str, Any]:
    """Tag a server-authored body with its frame type, checking it against the table.

    The field check is against `FRAME_TABLE`, so a reply that grew or lost a field
    relative to the frozen contract fails here rather than reaching a browser that then
    reads a missing key as a null value.

    Args:
        frame_type: The server-to-client frame being sent.
        body: The frame's fields.

    Returns:
        (dict[str, Any]) The tagged envelope.

    Raises:
        WsError: If the body's fields are not exactly the contract's fields.
    """
    expected = set(FRAME_TABLE[frame_type].fields)
    if set(body) != expected:
        raise WsError(f"{frame_type.value!r} carries fields {sorted(expected)}; got {sorted(body)}")
    return {ENVELOPE_TYPE_FIELD: frame_type.value, **body}


__all__ = [
    "CommandSink",
    "DispatchOutcome",
    "FrameDispatcher",
    "WsClosure",
]
