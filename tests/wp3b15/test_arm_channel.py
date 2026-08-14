"""Mounting the channel over an arm session: the stop lands, and a command is refused.

This is the wiring `oa-serve` installs, exercised through the socket rather than through the
objects. Two properties matter and they pull in opposite directions, which is why both are here:

- The soft stop must reach the arm session's latch — the same latch the deadman drives. A stop
  that engaged a second latch would be a control the operator believes acted, and `FR-GUI-065`
  puts that control in front of every role including one that holds no control authority.
- A `command` must be refused where the operator can see it, because this host reads the arm and
  does not command it. Silence there is the same defect wearing the other face.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.actuation.clock import ManualClock
from backend.actuation.guard import GuardSample
from backend.actuation.session import ArmSession
from backend.config.constants import DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT
from backend.ws import (
    ENVELOPE_TYPE_FIELD,
    ORIGIN_HEADER,
    REALTIME_ROUTE,
    WS_CLOSE_COMMAND_UNROUTABLE,
    mount_realtime_channel,
)
from backend.ws.arm_channel import READ_ONLY_HOST_REASON, refuse_command
from backend.ws.deployment import LoopbackDeployment
from contracts.prim.schema import ARM_SIDES
from contracts.units import Deg, Nm
from contracts.ws import LEASE_SESSION_FIELD, WsFrameType, WsRole
from tests.wp3b15.conftest import DEFAULT_SESSION_ID, expect_close, stop_frame

LOOPBACK_ORIGIN = f"http://{DEFAULT_HTTP_HOST}:{DEFAULT_HTTP_PORT}"

LEFT = ARM_SIDES[0]

RESTING_POSE_DEG = 3.0
RESTING_TORQUE_NM = 0.25
JOINT_COUNT = 8


def _resting_frame() -> tuple[tuple[Deg, ...], tuple[Nm, ...], GuardSample]:
    """One healthy read of an arm holding still."""
    return (
        tuple(Deg(RESTING_POSE_DEG) for _ in range(JOINT_COUNT)),
        tuple(Nm(RESTING_TORQUE_NM) for _ in range(JOINT_COUNT)),
        GuardSample.healthy(),
    )


def _mounted() -> tuple[TestClient, ArmSession]:
    """Mount the channel the way `oa-serve` does: over one arm session, loopback deployment."""
    clock = ManualClock()
    arm = ArmSession(clock=clock, read_arms={LEFT: _resting_frame})
    client = TestClient(FastAPI())
    mount_realtime_channel(
        client.app,
        latch_target=arm,
        deadman=arm.deadman,
        clock=clock,
        command_sink=refuse_command,
        security=LoopbackDeployment(host=DEFAULT_HTTP_HOST, origin_allowlist=(LOOPBACK_ORIGIN,)),
    )
    return client, arm


def _connect(client: TestClient, role: WsRole):
    """Open one connection in the given role from an admitted origin."""
    return client.websocket_connect(
        f"{REALTIME_ROUTE}?role={role.value}&{LEASE_SESSION_FIELD}={DEFAULT_SESSION_ID}",
        headers={ORIGIN_HEADER: LOOPBACK_ORIGIN},
    )


def test_a_stop_over_the_socket_engages_the_arm_sessions_latch() -> None:
    """The wire reaches the one latch, attributed to the session that sent it."""
    client, arm = _mounted()

    with client, _connect(client, WsRole.OPERATOR) as socket:
        socket.send_json(stop_frame())

    assert arm.latch_active
    assert arm.deadman.latched
    assert arm.latch_reason is not None
    assert DEFAULT_SESSION_ID in arm.latch_reason.gate_id


def test_an_observer_can_stop_this_arm() -> None:
    """`FR-GUI-065` — the soft stop is not a control-authority privilege.

    Asserted over the socket in the observer role rather than on the authorisation table,
    because what the requirement is about is the operator finding the button works.
    """
    client, arm = _mounted()

    with client, _connect(client, WsRole.OBSERVER) as socket:
        socket.send_json(stop_frame())

    assert arm.latch_active


def test_an_observers_command_is_refused_by_the_server() -> None:
    """`WP-3B-15` ⑥ — the other half: the same role that may stop may not command."""
    client, _ = _mounted()

    with client, _connect(client, WsRole.OBSERVER) as socket:
        socket.send_json({ENVELOPE_TYPE_FIELD: WsFrameType.COMMAND.value})
        refusal = expect_close(socket)

    assert refusal.code != WS_CLOSE_COMMAND_UNROUTABLE


def test_an_operators_command_is_refused_because_this_host_cannot_deliver_it() -> None:
    """Authorised and undeliverable are different refusals, and the reason says which.

    An operator holds the authority, so nothing about the frame is wrong. What is missing is a
    send path in this process, and the close reason names that rather than the frame — an
    operator told "unauthorised" goes looking for a permission they already have.
    """
    client, _ = _mounted()

    with client, _connect(client, WsRole.OPERATOR) as socket:
        socket.send_json({ENVELOPE_TYPE_FIELD: WsFrameType.COMMAND.value})
        refusal = expect_close(socket)

    assert refusal.code == WS_CLOSE_COMMAND_UNROUTABLE
    assert READ_ONLY_HOST_REASON in refusal.reason
