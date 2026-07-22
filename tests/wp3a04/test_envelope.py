"""WP-3A-04 — the single-WS envelope: one channel, lease-first queues, backpressure, roles, health.

`02b` §5.2 WP-3A-04 acceptance ①②⑥⑦⑧ are exercised here against the typed surface:
the realtime channel is one WebSocket; a camera flood cannot outrank a lease (the
head-of-line mitigation the single-WS design rests on); backpressure sheds the
camera and protects the lease/command/telemetry; the control channel refuses
plaintext and wildcard Origin; an observer's control send is refused server-side;
and the public health payload never leaks the control holder or the active profile.
"""

from __future__ import annotations

import pytest

import contracts.ws as ws


def test_exactly_one_realtime_channel_no_parallel_stacks() -> None:
    """The realtime channel is a single WebSocket; no parallel transport stack is admitted (①)."""
    envelope = ws.canonical_envelope()
    assert envelope["transport"]["realtime_channel"] == "websocket"
    assert envelope["transport"]["single_realtime_channel"] is True
    assert set(ws.FORBIDDEN_PARALLEL_STACKS) == {"webrtc", "foxglove", "rosbridge", "grpc-web"}


def test_frame_set_is_the_single_multiplexed_set() -> None:
    """The nine frame types are the one set the single WS multiplexes."""
    assert {frame.value for frame in ws.WsFrameType} == {
        "telemetry",
        "command",
        "camera",
        "lease_renew",
        "lease_grant",
        "lease_reject",
        "rearm_issue",
        "rearm_confirm",
        "rearm_accept",
    }
    assert set(ws.FRAME_TABLE) == set(ws.WsFrameType)


def test_lease_outranks_camera_and_command_and_telemetry() -> None:
    """The lease class is strictly highest priority, so a camera flood cannot delay it (②)."""
    lease = ws.FRAME_TABLE[ws.WsFrameType.LEASE_RENEW].priority
    command = ws.FRAME_TABLE[ws.WsFrameType.COMMAND].priority
    telemetry = ws.FRAME_TABLE[ws.WsFrameType.TELEMETRY].priority
    camera = ws.FRAME_TABLE[ws.WsFrameType.CAMERA].priority
    assert int(lease) < int(command) < int(telemetry) < int(camera)
    assert all(
        ws.FRAME_TABLE[frame].priority == lease
        for frame in ws.WsFrameType
        if frame.name.startswith(("LEASE", "REARM"))
    )


def test_camera_is_dropped_under_backpressure_lease_is_not() -> None:
    """Over the bufferedAmount threshold the camera is shed and the lease is protected (②/⑦)."""
    over = ws.BUFFERED_AMOUNT_THRESHOLD_BYTES + 1
    assert ws.should_drop_under_backpressure(ws.WsFrameType.CAMERA, over) is True
    for protected in ws.BACKPRESSURE_PROTECTED_FRAMES:
        assert ws.should_drop_under_backpressure(protected, over) is False


def test_camera_is_not_dropped_below_threshold() -> None:
    """Below the threshold nothing is shed; backpressure engages only when the buffer fills."""
    assert ws.should_drop_under_backpressure(ws.WsFrameType.CAMERA, 0) is False


def test_security_requires_wss_allowlist_and_csrf() -> None:
    """A valid control-channel policy is WSS over TLS with a named Origin allowlist and CSRF (⑦)."""
    policy = ws.WsSecurityPolicy(
        scheme="wss", origin_allowlist=("https://arm.local",), csrf_cors_enforced=True
    )
    assert policy.scheme == "wss"


@pytest.mark.parametrize(
    ("scheme", "origins", "csrf"),
    [
        ("ws", ("https://arm.local",), True),
        ("wss", ("*",), True),
        ("wss", (), True),
        ("wss", ("https://arm.local",), False),
    ],
)
def test_security_refuses_plaintext_wildcard_empty_and_no_csrf(
    scheme: str, origins: tuple[str, ...], csrf: bool
) -> None:
    """Plaintext, a wildcard Origin, an empty allowlist and missing CSRF are each refused (⑦)."""
    with pytest.raises(ws.WsError):
        ws.WsSecurityPolicy(scheme=scheme, origin_allowlist=origins, csrf_cors_enforced=csrf)


def test_observer_send_of_a_control_frame_is_refused() -> None:
    """An observer's command, renewal or re-arm confirmation is refused server-side (⑥)."""
    for frame in (ws.WsFrameType.COMMAND, ws.WsFrameType.LEASE_RENEW, ws.WsFrameType.REARM_CONFIRM):
        with pytest.raises(ws.WsError):
            ws.authorize_send(ws.WsRole.OBSERVER, frame)


def test_operator_may_send_control_frames_observer_may_subscribe() -> None:
    """The single operator holds command authority; an observer still receives telemetry/camera."""
    ws.authorize_send(ws.WsRole.OPERATOR, ws.WsFrameType.COMMAND)
    ws.authorize_send(ws.WsRole.OPERATOR, ws.WsFrameType.LEASE_RENEW)
    ws.authorize_send(ws.WsRole.OBSERVER, ws.WsFrameType.TELEMETRY)
    ws.authorize_send(ws.WsRole.OBSERVER, ws.WsFrameType.CAMERA)


def test_public_health_never_leaks_control_holder_or_active_profile() -> None:
    """The public health payload is stripped of the control holder and active profile (⑧)."""
    internal = {"status": "ok", "control_holder": "op-1", "active_profile": "weld-A"}
    assert set(ws.health_leaks(internal)) == {"control_holder", "active_profile"}
    projected = ws.public_health(internal)
    assert projected == {"status": "ok"}
    assert ws.health_leaks(projected) == ()


def test_camera_tag_carries_the_ctr_prim_camera_identifier_join() -> None:
    """A camera binary frame's tag round-trips the CTR-PRIM camera identifier (FR-GUI-040)."""
    from contracts.prim import FrameType, arm_slot

    slot = arm_slot("right", "wrist")
    tag = ws.camera_frame_tag(slot, FrameType.DEPTH)
    assert tag == "right_wrist:depth"
    assert ws.slot_from_camera_frame_tag(tag) == slot


def test_reverify_confirms_the_generated_body() -> None:
    """The reverify hook confirms the generated body agrees with CTR-PRIM@v1 and the mirror."""
    report = ws.reverify()
    assert report.confirmed, report.mismatches
