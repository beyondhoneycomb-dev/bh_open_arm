"""Shared fixtures for the WP-3B-15 tests — real latch, real lease, no socket.

Nothing safety-bearing is doubled here. The latch is the production one-way
`backend.actuation.latch.SafetyLatch`, and the lease is the production
`backend.deadman.DeadmanController` over the production `LeaseManager`. The only
adaptation is `SafetyLatchTarget`, which maps `SafetyLatch`'s three methods onto the
three `LatchTarget` names the deadman drives — the same adaptation production already
does in `backend/freedrive/session.py:244-269`, for the same reason. So a test that sees
the latch engage has seen the real latch engage, and `SafetyLatch.reason` is the real
recorded attribution rather than a count kept by a double.

`TestClient` speaks ASGI in-process and binds no port, so these tests open no socket and
race no scheduler. The clock is a `ManualClock`, which is what makes "the lease lapsed"
a stated fact rather than a wall-clock race.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest

# `WebSocketDisconnect` comes through `fastapi`, not `starlette.websockets` where the
# class is defined: FastAPI re-exports the same object and is the dependency this project
# declares, so importing it here rests on no requirement list but our own.
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient

from backend.actuation.clock import ManualClock
from backend.actuation.latch import SafetyLatch
from backend.actuation.lease import LeaseManager
from backend.deadman import DEADMAN_LEASE_DURATION_SEC, DeadmanController, LeaseRenewal
from backend.security.constants import SECURE_HTTP_SCHEME
from backend.security.origin_policy import ControlChannelSecurity, RestCorsPolicy
from backend.ws import (
    ENVELOPE_TYPE_FIELD,
    ORIGIN_HEADER,
    REALTIME_ROUTE,
    WsSession,
    mount_realtime_channel,
)
from contracts.prim import LEASE_ISSUED_FIELD
from contracts.ws import (
    LEASE_GENERATION_FIELD,
    LEASE_SEQUENCE_FIELD,
    LEASE_SESSION_FIELD,
    WS_SECURE_SCHEME,
    WsFrameType,
    WsRole,
    WsSecurityPolicy,
)
from ops.cancel.scheduler import LatchReason

DEFAULT_SESSION_ID = "session-under-test"

# The one origin these tests are served from. It is `https`, and the policy below is
# `wss`, because `FR-OPS-090` admits no other shape — `ControlChannelSecurity` refuses to
# be constructed with a plaintext scheme or a plaintext origin. That is not a convenience
# chosen for the fixture: it is the only policy the type permits, and
# `test_transport_security.py` is where that constraint is pinned rather than assumed.
ALLOWED_ORIGIN = "https://127.0.0.1:8000"
FORBIDDEN_ORIGIN = "https://evil.example"

TEST_CONTROL_SECURITY = ControlChannelSecurity(
    ws=WsSecurityPolicy(
        scheme=WS_SECURE_SCHEME,
        origin_allowlist=(ALLOWED_ORIGIN,),
        csrf_cors_enforced=True,
    ),
    rest=RestCorsPolicy(
        rest_scheme=SECURE_HTTP_SCHEME,
        allowed_origins=(ALLOWED_ORIGIN,),
        csrf_enforced=True,
    ),
)

# Liveness bound on a read that is expected to find a close already queued. It is not
# synchronisation and the passing path never waits on it: by the time a refusal test
# reads, the frames it sent and the close they earned are already in the client's queue,
# so the read returns immediately. The bound exists because `WebSocketTestSession.receive`
# takes no timeout, so a server that wrongly accepted the frame would block the read
# forever — and a suite that wedges reports nothing, while a suite that fails reports
# exactly which rule broke.
CLOSE_TIMEOUT_SEC = 5.0


class SafetyLatchTarget:
    """The `LatchTarget` surface over the production one-way `SafetyLatch`.

    `SafetyLatch` names its methods `engage`/`acknowledge`/`is_active`; the deadman drives
    `engage_safety_latch`/`acknowledge_latch`/`latch_active`. This is that rename and
    nothing else — no state of its own, no second latch — mirroring the adapter
    `FreedriveSession` already carries in production.
    """

    def __init__(self, latch: SafetyLatch) -> None:
        """Bind the surface to the one latch it renames.

        Args:
            latch: The production safety latch every source engages.
        """
        self._latch = latch

    @property
    def latch_active(self) -> bool:
        """Whether the latch is currently held."""
        return self._latch.is_active

    def engage_safety_latch(self, reason: LatchReason) -> None:
        """Engage the latch; the latch itself keeps the first reason."""
        self._latch.engage(reason)

    def acknowledge_latch(self) -> None:
        """Clear the latch — the operator/re-arm release."""
        self._latch.acknowledge()


@dataclass
class WsFixture:
    """The server under test and the real safety state behind it.

    Attributes:
        client: The in-process ASGI client; binds no port.
        latch: The production one-way latch a stop and an expiry both engage.
        target: The `LatchTarget` rename over `latch`, held so a test mounting a second
            application passes the same surface rather than building a second one.
        deadman: The lease canon, built over the same latch surface.
        lease: The `LeaseManager` the deadman renews.
        clock: The manual server clock the latch and the lease share.
        commands: Every command frame the dispatcher routed, in arrival order.
        sessions: Every session a routed command arrived on, in arrival order.
    """

    client: TestClient
    latch: SafetyLatch
    target: SafetyLatchTarget
    deadman: DeadmanController
    lease: LeaseManager
    clock: ManualClock
    commands: list[Mapping[str, Any]] = field(default_factory=list)
    sessions: list[WsSession] = field(default_factory=list)


@pytest.fixture
def ws() -> Iterator[WsFixture]:
    """The mounted realtime channel over a real latch, a real lease and a manual clock."""
    clock = ManualClock()
    latch = SafetyLatch()
    target = SafetyLatchTarget(latch)
    lease = LeaseManager(DEADMAN_LEASE_DURATION_SEC)
    deadman = DeadmanController(lease=lease, latch_target=target, clock=clock)
    fixture = WsFixture(
        client=TestClient(FastAPI()),
        latch=latch,
        target=target,
        deadman=deadman,
        lease=lease,
        clock=clock,
    )

    def record(session: WsSession, payload: Mapping[str, Any]) -> None:
        """The host's command sink: record what was routed and on whose session."""
        fixture.sessions.append(session)
        fixture.commands.append(payload)

    mount_realtime_channel(
        fixture.client.app,
        latch_target=target,
        deadman=deadman,
        clock=clock,
        command_sink=record,
        security=TEST_CONTROL_SECURITY,
    )
    with fixture.client:
        yield fixture


def connect(
    fixture: WsFixture,
    role: WsRole,
    session_id: str = DEFAULT_SESSION_ID,
    origin: str | None = ALLOWED_ORIGIN,
) -> Any:
    """Open one client connection in the given role.

    Args:
        fixture: The mounted server.
        role: The role this connection claims at the handshake.
        session_id: The session identifier the connection carries.
        origin: The `Origin` header to send, or None to send none. Defaults to an
            allowlisted origin so a test about roles is not also a test about origins.

    Returns:
        (Any) The `TestClient` websocket context manager.
    """
    headers = {} if origin is None else {ORIGIN_HEADER: origin}
    return fixture.client.websocket_connect(
        f"{REALTIME_ROUTE}?role={role.value}&{LEASE_SESSION_FIELD}={session_id}",
        headers=headers,
    )


def frame(frame_type: WsFrameType, **fields: Any) -> dict[str, Any]:
    """Build a client-authored envelope for a frame type.

    Args:
        frame_type: The frame being sent.
        **fields: The frame's wire fields.

    Returns:
        (dict[str, Any]) The tagged envelope.
    """
    return {ENVELOPE_TYPE_FIELD: frame_type.value, **fields}


def stop_frame(session_id: str = DEFAULT_SESSION_ID) -> dict[str, Any]:
    """The soft-stop envelope: a session id for attribution and nothing else."""
    return frame(WsFrameType.STOP_HOLD, **{LEASE_SESSION_FIELD: session_id})


def renew_frame(
    generation: int, sequence: int, issued: float, session_id: str = DEFAULT_SESSION_ID
) -> dict[str, Any]:
    """The lease-renewal envelope, carrying no expiry (the client cannot author one)."""
    return frame(
        WsFrameType.LEASE_RENEW,
        **{
            LEASE_SESSION_FIELD: session_id,
            LEASE_GENERATION_FIELD: generation,
            LEASE_SEQUENCE_FIELD: sequence,
            LEASE_ISSUED_FIELD: issued,
        },
    )


def expect_close(socket: Any) -> WebSocketDisconnect:
    """Read the close the server owes this connection, and return it.

    Args:
        socket: The client's websocket session.

    Returns:
        (WebSocketDisconnect) The close, carrying `code` and `reason`.

    Raises:
        AssertionError: If the server sent a frame instead of closing, or sent nothing
            within `CLOSE_TIMEOUT_SEC`.
    """
    outcome: list[Any] = []

    def read() -> None:
        """Read one server message, keeping either the frame or the close it raised."""
        try:
            outcome.append(socket.receive_json())
        except WebSocketDisconnect as closed:
            outcome.append(closed)

    # A daemon thread, not a pool: a pool's shutdown joins its workers, so a reader that
    # is genuinely stuck would move the hang from this call to interpreter exit instead
    # of removing it.
    reader = threading.Thread(target=read, name="wp3b15-close-reader", daemon=True)
    reader.start()
    reader.join(timeout=CLOSE_TIMEOUT_SEC)
    if reader.is_alive():
        pytest.fail(
            f"the server neither replied nor closed within {CLOSE_TIMEOUT_SEC}s; "
            "a refused frame must be refused visibly"
        )
    delivered = outcome[0]
    if isinstance(delivered, WebSocketDisconnect):
        return delivered
    pytest.fail(f"expected a close, got the frame {delivered!r}")


def take_deadman(fixture: WsFixture, sequence: int = 1) -> None:
    """Take the deadman for the current generation, so the lease is live.

    Sent through the controller rather than the socket: this is setup, and a test that
    builds its precondition through the surface it is about to judge cannot tell a broken
    precondition from a broken surface.

    Args:
        fixture: The mounted server.
        sequence: The renewal sequence, strictly increasing per generation.
    """
    result = fixture.deadman.receive_renewal(
        LeaseRenewal(
            generation=fixture.deadman.current_generation,
            sequence=sequence,
            issued_mono_client=fixture.clock.now(),
        )
    )
    assert result.accepted, f"setup renewal was refused: {result.decision}"
