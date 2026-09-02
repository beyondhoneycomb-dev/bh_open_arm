"""CTR-WS@v2 — the single-WebSocket envelope, transported over one realtime channel.

`02b` §5.2 WP-3A-04 fixes what this module is: the one realtime browser<->backend
transport (D-2), multiplexing telemetry, command, camera-binary, soft-stop and
control-lease frames on a single WebSocket. It has two disciplines it may never
break, and both are the `FAIL_BLOCKING` defect of this WP:

1. It CONSUMES `CTR-PRIM@v1` and redefines none of its six primitives. The camera
   identifier, the timestamp/clock ownership, the frame-type tag, the queue
   semantics and the error envelope are imported from `contracts.prim`; a WS that
   restated any of them would fork the contract five ways (`02b` §5.0b).
2. It TRANSPORTS the dead-man lease and does not redefine it. The lease semantics
   are `WP-2A-02`'s canon (`backend.deadman`, U-4): the server clock is the sole
   expiry judge, a latched lease resumes only through the re-arm handshake, a
   replay/stale/forged generation is refused, and a renewal delayed past
   `max_lease_age` is discarded. This module names the lease fields on the wire —
   using the field names `CTR-PRIM@v1` pinned (`expiry_mono_server` on the server
   clock, `issued_mono_client` on the client clock) — but owns none of that logic.
   The `contracts` tree and the `backend/deadman` tree do not import each other
   (`06` §5.6 contract join); the transport-vs-canon agreement is proven by test,
   offset by `CONTRACT_FROZEN` + CI-09.

The one structural guarantee that makes acceptance ⑤ (expiry never judged on the
client clock) unbreakable: no client-authored frame carries an expiry field at all.
The field simply does not exist on anything a client sends, mirroring
`backend.deadman.LeaseRenewal`, so no server path can read a client-supplied expiry.

`contracts/ws/envelope.schema.json` is the frozen, language-agnostic mirror of this
module (`CONTRACT_FROZEN`, frozen by `WP-3A-06`); `reverify.py` proves the two, and
`CTR-PRIM@v1`, stay consistent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from contracts.prim import (
    CONTRACT_ID as PRIM_CONTRACT_ID,
)
from contracts.prim import (
    EXPIRY_JUDGE_ROLE,
    LEASE_EXPIRY_FIELD,
    LEASE_ISSUED_FIELD,
    WS_TAG_SEPARATOR,
    CameraSlotKey,
    ClockRole,
    FrameType,
    PriorityClass,
    QueueSemantics,
    slot_from_ws_tag,
    verify_expiry_owner,
)
from contracts.prim import (
    QUEUE_PROFILES as PRIM_QUEUE_PROFILES,
)

# The contract id this module and its JSON mirror are the body of. Freeze checks,
# staleness and the no-redefinition scan key on this exact string.
CONTRACT_ID = "CTR-WS@v2"

# The human title and description carried into the generated frozen body.
CONTRACT_TITLE = "OpenArm single-WebSocket envelope (CTR-WS@v2)"
CONTRACT_DESCRIPTION = (
    "The one realtime browser<->backend transport (D-2): a single WebSocket "
    "multiplexing telemetry, command, camera-binary, soft-stop and control-lease "
    "frames. Consumes CTR-PRIM@v1 by reference and redefines none of its "
    "primitives. Transports the WP-2A-02 dead-man lease; it does NOT redefine the "
    "lease semantics. This body is generated from contracts/ws/schema.py by "
    "canonical_envelope(); WP-3A-06 freezes it by content hash (CI-09)."
)

# The frozen generation. A change to the envelope is a new generation
# (`CTR-WS@v3`), never an in-place edit (`06` §4.3).
SCHEMA_VERSION = 2

# The one contract this envelope consumes by reference. Named so a bump of it
# propagates staleness here (`CR-2`), and so consumers can assert the join.
CONSUMED_CONTRACTS = (PRIM_CONTRACT_ID,)


class WsError(RuntimeError):
    """Raised when a WS envelope rule is violated at the contract surface."""


# ---------------------------------------------------------------------------
# Transport — exactly one realtime channel (D-2)
# ---------------------------------------------------------------------------

# The single realtime channel. A parallel realtime stack is forbidden (D-2); gRPC
# is reserved for backend<->remote-inference and is not a browser channel.
REALTIME_CHANNEL = "websocket"
FORBIDDEN_PARALLEL_STACKS = ("webrtc", "foxglove", "rosbridge", "grpc-web")


class FrameDirection(StrEnum):
    """Which way a frame travels on the single WebSocket."""

    CLIENT_TO_SERVER = "client_to_server"
    SERVER_TO_CLIENT = "server_to_client"


class FramePayload(StrEnum):
    """Whether a frame is a text frame or a binary frame on the wire (§2.4)."""

    TEXT = "text"
    BINARY = "binary"


class WsFrameType(StrEnum):
    """The single set of frame types the one WebSocket multiplexes (`02b` §5.2).

    Telemetry, command and camera-binary are the three application classes; the six
    lease/re-arm frames transport the dead-man lease and its resume handshake.
    `STOP_HOLD` is the soft stop, which is a fourth kind: a state-changing frame that
    carries no command authority, so an observer may send it (`13` FR-GUI-065).
    """

    TELEMETRY = "telemetry"
    COMMAND = "command"
    CAMERA = "camera"
    STOP_HOLD = "stop_hold"
    LEASE_RENEW = "lease_renew"
    LEASE_GRANT = "lease_grant"
    LEASE_REJECT = "lease_reject"
    REARM_ISSUE = "rearm_issue"
    REARM_CONFIRM = "rearm_confirm"
    REARM_ACCEPT = "rearm_accept"


# ---------------------------------------------------------------------------
# The control lease — transported, never redefined (WP-2A-02 canon)
# ---------------------------------------------------------------------------

# The WS-transport field names of the control lease. The expiry and issued fields
# are NOT named here: they are `CTR-PRIM@v1`'s pins (`LEASE_EXPIRY_FIELD` on the
# server clock, `LEASE_ISSUED_FIELD` on the client clock), referenced so their
# clock ownership has one definition. `lease_generation` is this transport's name
# for the canon's `generation` (the join is asserted by test against backend.deadman).
LEASE_SESSION_FIELD = "session_id"
LEASE_GENERATION_FIELD = "lease_generation"
LEASE_SEQUENCE_FIELD = "sequence"
LEASE_REASON_FIELD = "reason"
# The canon field name `lease_generation` maps to on the dead-man side.
LEASE_GENERATION_CANON_FIELD = "generation"
# The age-filter bound the WS carries so a delayed renewal is discarded, not honoured.
MAX_LEASE_AGE_FIELD = "max_lease_age"

# The `telemetry` body. Two consumers were already written against this frame before it carried
# anything, and they want different things: `S-03` reads per-motor diagnostics, and the policy
# path reads the frozen 48-channel observation vector. Both are on the board — the bus answers
# five channels in the refresh the pose came in — so the frame carries both rather than making
# one of the two screens wrong.
#
# `sequence` is the session tick, not a per-frame counter: a client that sees it jump knows the
# gap is the loop's, and one that sees it stand still knows the board stopped advancing. A
# counter of the sender's own could not say either.
TELEMETRY_SEQUENCE_FIELD = "sequence"
# `{"observation.state": [...]}` — the 48 channels of `openarm_observation_features`, in that
# declaration order. An object rather than a bare list so a second observation key (images,
# meta) is an added key rather than a reshaped frame.
TELEMETRY_OBSERVATION_FIELD = "observation"
# Per-motor rows carrying what the observation vector has no channel for: the two temperatures.
# Empty when the source has no thermometer, which is what a CAN-free double is — the list says
# "no motor reported one", never "every motor reads zero".
TELEMETRY_MOTOR_STATES_FIELD = "motor_states"
# Per-side liveness: the guard sample and the age of the reading it came from. Without it a
# client cannot tell a board that stopped advancing from an arm that is holding still, because
# every value in the two cases is identical.
TELEMETRY_ARMS_FIELD = "arms"
# Per-joint operator readout: the reading in both units, the soft limits it is judged against,
# and the two verdicts `04` FR-MAN-013 forbids the screen from computing — near-limit and the
# refused jog direction. Separate from `observation` because the two answer to different owners:
# that vector is the frozen LeRobot channel list a policy eats, in its names and its unit, and
# this is the operator's view in the URDF namespace with the bounds beside the values. Both come
# off one board read, so they cannot describe different instants.
TELEMETRY_JOINTS_FIELD = "joints"


class LeaseRejectReason(StrEnum):
    """The wire reason a renewal was refused or discarded (transports RenewalDecision).

    One reason per refusal, never a bare "rejected": the audit must tell a replay
    from an aged message from a latched refusal, because they mean different things
    about the operator and the link. These values mirror the non-accepted
    `backend.deadman.RenewalDecision` members by value; the agreement is asserted by
    test, since the two trees do not import each other (`06` §5.6).
    """

    REJECTED_LATCHED = "rejected_latched"
    REJECTED_UNARMED = "rejected_unarmed"
    REJECTED_STALE_GENERATION = "rejected_stale_generation"
    REJECTED_UNKNOWN_GENERATION = "rejected_unknown_generation"
    REJECTED_REPLAY = "rejected_replay"
    DISCARDED_AGED = "discarded_aged"


# The three re-arm frames, in the only order a latched lease resumes: the server
# issues a generation, the operator confirms, the server accepts. A post-expiry
# renewal never resumes motion; only this handshake does (`backend.deadman.rearm`).
REARM_HANDSHAKE_FRAMES = (
    WsFrameType.REARM_ISSUE,
    WsFrameType.REARM_CONFIRM,
    WsFrameType.REARM_ACCEPT,
)


# ---------------------------------------------------------------------------
# The frame table — one row per frame type, bound to a CTR-PRIM queue class
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrameSpec:
    """One frame type's transport rules, bound to a `CTR-PRIM@v1` queue class.

    Priority is not restated here; it is read from the bound queue (`queue.priority`),
    so the lease-first ordering has one definition — `CTR-PRIM@v1`'s `PriorityClass`
    — and cannot drift between this table and the primitive.

    Attributes:
        frame_type: The frame type this row describes.
        direction: Which way it travels on the single WebSocket.
        payload: Whether it is a text or binary frame.
        queue: The bounded `CTR-PRIM@v1` queue class it is delivered through.
        is_control_frame: Whether sending it requires command authority (an observer
            holds none). This is an authority test, not a "changes robot state" test:
            telemetry and camera are read-only and so are not control frames, and the
            soft stop changes state yet is not one either, because `13` FR-GUI-065
            puts it within reach of a client that holds no control.
        fields: The wire field names this frame carries, in declaration order.
    """

    frame_type: WsFrameType
    direction: FrameDirection
    payload: FramePayload
    queue: QueueSemantics
    is_control_frame: bool
    fields: tuple[str, ...]

    @property
    def priority(self) -> PriorityClass:
        """This frame's delivery priority, read from its bound queue (lease first)."""
        return self.queue.priority


# The single frame-type set. Queue bindings reference `CTR-PRIM@v1` QUEUE_PROFILES,
# so every priority and drop policy has one definition point. Client lease frames
# (`LEASE_RENEW`, `REARM_CONFIRM`) deliberately omit `LEASE_EXPIRY_FIELD`: a client
# cannot author an expiry, which is what makes acceptance ⑤ structural.
FRAME_TABLE: dict[WsFrameType, FrameSpec] = {
    WsFrameType.TELEMETRY: FrameSpec(
        frame_type=WsFrameType.TELEMETRY,
        direction=FrameDirection.SERVER_TO_CLIENT,
        payload=FramePayload.TEXT,
        queue=PRIM_QUEUE_PROFILES["telemetry"],
        is_control_frame=False,
        fields=(
            TELEMETRY_SEQUENCE_FIELD,
            TELEMETRY_OBSERVATION_FIELD,
            TELEMETRY_MOTOR_STATES_FIELD,
            TELEMETRY_ARMS_FIELD,
            TELEMETRY_JOINTS_FIELD,
        ),
    ),
    WsFrameType.COMMAND: FrameSpec(
        frame_type=WsFrameType.COMMAND,
        direction=FrameDirection.CLIENT_TO_SERVER,
        payload=FramePayload.TEXT,
        queue=PRIM_QUEUE_PROFILES["command"],
        is_control_frame=True,
        fields=(),
    ),
    WsFrameType.CAMERA: FrameSpec(
        frame_type=WsFrameType.CAMERA,
        direction=FrameDirection.SERVER_TO_CLIENT,
        payload=FramePayload.BINARY,
        queue=PRIM_QUEUE_PROFILES["camera_preview"],
        is_control_frame=False,
        fields=(),
    ),
    WsFrameType.STOP_HOLD: FrameSpec(
        frame_type=WsFrameType.STOP_HOLD,
        direction=FrameDirection.CLIENT_TO_SERVER,
        payload=FramePayload.TEXT,
        # The command class, NOT the lease class. The lease queue is capacity 1 with
        # LATEST_WINS (`CTR-PRIM@v1`), so a queued stop would be evicted by the very
        # next renewal — and renewals never stop arriving, which makes that loss a
        # certainty rather than a race. The command queue is capacity 8 DROP_OLDEST,
        # where an arriving stop is the newest and so is never the evicted item.
        # What this costs: the stop is drained after the lease class (one small
        # frame) and shares a queue with jog commands, so eight command frames
        # arriving between two drains could still evict it. That residue closes only
        # with a stop-only queue class, which `CTR-PRIM@v1` does not have; adding one
        # bumps CTR-PRIM and the five contracts that consume it.
        queue=PRIM_QUEUE_PROFILES["command"],
        # Not a control frame. `is_control_frame` gates command AUTHORITY, and `13`
        # FR-GUI-065 puts the stop within reach independently of who holds control.
        # Marking it True would make that requirement unsatisfiable, since
        # `authorize_send` would refuse the frame from the very observers it is
        # written for.
        is_control_frame=False,
        # The session is carried for attribution only — who pressed it. Nothing on
        # this frame decides anything: the server stamps the time and the reason,
        # because a client-supplied cause on a safety path is a forgeable audit.
        fields=(LEASE_SESSION_FIELD,),
    ),
    WsFrameType.LEASE_RENEW: FrameSpec(
        frame_type=WsFrameType.LEASE_RENEW,
        direction=FrameDirection.CLIENT_TO_SERVER,
        payload=FramePayload.TEXT,
        queue=PRIM_QUEUE_PROFILES["lease"],
        is_control_frame=True,
        fields=(
            LEASE_SESSION_FIELD,
            LEASE_GENERATION_FIELD,
            LEASE_SEQUENCE_FIELD,
            LEASE_ISSUED_FIELD,
        ),
    ),
    WsFrameType.LEASE_GRANT: FrameSpec(
        frame_type=WsFrameType.LEASE_GRANT,
        direction=FrameDirection.SERVER_TO_CLIENT,
        payload=FramePayload.TEXT,
        queue=PRIM_QUEUE_PROFILES["lease"],
        is_control_frame=False,
        fields=(
            LEASE_SESSION_FIELD,
            LEASE_GENERATION_FIELD,
            LEASE_EXPIRY_FIELD,
            LEASE_SEQUENCE_FIELD,
            LEASE_ISSUED_FIELD,
        ),
    ),
    WsFrameType.LEASE_REJECT: FrameSpec(
        frame_type=WsFrameType.LEASE_REJECT,
        direction=FrameDirection.SERVER_TO_CLIENT,
        payload=FramePayload.TEXT,
        queue=PRIM_QUEUE_PROFILES["lease"],
        is_control_frame=False,
        fields=(LEASE_SESSION_FIELD, LEASE_GENERATION_FIELD, LEASE_REASON_FIELD),
    ),
    WsFrameType.REARM_ISSUE: FrameSpec(
        frame_type=WsFrameType.REARM_ISSUE,
        direction=FrameDirection.SERVER_TO_CLIENT,
        payload=FramePayload.TEXT,
        queue=PRIM_QUEUE_PROFILES["lease"],
        is_control_frame=False,
        fields=(LEASE_SESSION_FIELD, LEASE_GENERATION_FIELD),
    ),
    WsFrameType.REARM_CONFIRM: FrameSpec(
        frame_type=WsFrameType.REARM_CONFIRM,
        direction=FrameDirection.CLIENT_TO_SERVER,
        payload=FramePayload.TEXT,
        queue=PRIM_QUEUE_PROFILES["lease"],
        is_control_frame=True,
        fields=(LEASE_SESSION_FIELD, LEASE_GENERATION_FIELD),
    ),
    WsFrameType.REARM_ACCEPT: FrameSpec(
        frame_type=WsFrameType.REARM_ACCEPT,
        direction=FrameDirection.SERVER_TO_CLIENT,
        payload=FramePayload.TEXT,
        queue=PRIM_QUEUE_PROFILES["lease"],
        is_control_frame=False,
        fields=(
            LEASE_SESSION_FIELD,
            LEASE_GENERATION_FIELD,
            LEASE_EXPIRY_FIELD,
            LEASE_SEQUENCE_FIELD,
            LEASE_ISSUED_FIELD,
        ),
    ),
}

# The lease frames a client authors. Named for the renewal loop, which needs to know
# which lease frames it emits; the expiry guarantee below does not read this tuple,
# because it must hold for every client-authored frame, not only the lease ones.
CLIENT_LEASE_FRAMES = (WsFrameType.LEASE_RENEW, WsFrameType.REARM_CONFIRM)


def camera_frame_tag(slot: CameraSlotKey, channel: FrameType) -> str:
    """Build the binary camera frame's `<slot>:<channel>` tag (`CTR-PRIM@v1` join).

    The tag is the camera identifier joined with the frame-type channel through the
    primitive's own `ws_tag`, so a preview frame carries the same slot key the CAM
    registry, the CAP sidecar and the REC feature key use.

    Args:
        slot: The camera slot key the frame belongs to.
        channel: The image channel (RGB or depth).

    Returns:
        (str) The multiplexing tag for the camera binary frame.
    """
    return slot.ws_tag(channel)


def slot_from_camera_frame_tag(tag: str) -> CameraSlotKey:
    """Recover the camera slot key from a binary camera frame tag (round-trip inverse).

    Args:
        tag: A `<slot>:<channel>` camera frame tag.

    Returns:
        (CameraSlotKey) The slot the tag carries.
    """
    return slot_from_ws_tag(tag)


# ---------------------------------------------------------------------------
# Expiry ownership — the WS transports it, the SERVER clock judges it
# ---------------------------------------------------------------------------


def assert_expiry_owner_is_server() -> None:
    """Confirm the WS agrees the server clock is the sole expiry judge.

    The WS transports the lease but cannot re-own who judges its expiry; that role
    is pinned to the server at the `CTR-PRIM@v1` level (`EXPIRY_JUDGE_ROLE`). This
    calls the primitive's own guard, so the WS states its agreement by reference and
    a drift to any other role is refused there, not re-decided here.

    Raises:
        PrimitiveRedefinitionError: If the pinned expiry judge is not the server.
    """
    verify_expiry_owner(EXPIRY_JUDGE_ROLE)


def client_frames_omit_expiry() -> bool:
    """Whether every client-authored frame omits the expiry field (acceptance ⑤).

    The set is derived from the frame table's directions rather than listed, so a
    frame added to the table is inside this guarantee the moment it exists. Listing
    it would put the newest frame — the one nobody has audited yet — outside the
    check that exists to stop a client from authoring an expiry.

    Returns:
        (bool) True when no frame a client may send carries `LEASE_EXPIRY_FIELD`.
    """
    return all(
        LEASE_EXPIRY_FIELD not in spec.fields
        for spec in FRAME_TABLE.values()
        if spec.direction is FrameDirection.CLIENT_TO_SERVER
    )


# ---------------------------------------------------------------------------
# Roles and command authority — one holder, observers rejected server-side
# ---------------------------------------------------------------------------


class WsRole(StrEnum):
    """The role a connected WS client holds (FR-OPS-078 separation).

    Exactly one operator holds command authority at a time; every other client is
    an observer, read-only. Admin adds force-release and envelope changes but is not
    a second command source.
    """

    OBSERVER = "observer"
    OPERATOR = "operator"
    ADMIN = "admin"


# The single role that may send control frames (`send_action`, lease renewals,
# re-arm confirmation). An observer holds none of these rights.
CONTROL_HOLDER_ROLE = WsRole.OPERATOR


def authorize_send(role: WsRole, frame_type: WsFrameType) -> None:
    """Refuse an observer's attempt to send a control frame, server-side (⑥).

    Command authority belongs to one holder; an observer subscribing to telemetry
    and camera may not write a command, a lease renewal or a re-arm confirmation.
    The refusal is server-side by contract, not a client-side courtesy.

    The soft stop passes for every role, and it does so through the frame table's
    `is_control_frame` rather than a branch here. A frame-type-granular rule can be
    checked statically and read off one table; an exception written into this
    function could not, and the next safety frame would need a second one.

    Args:
        role: The sending client's role.
        frame_type: The frame the client is trying to send.

    Raises:
        WsError: If a non-operator sends a control frame.
    """
    if FRAME_TABLE[frame_type].is_control_frame and role is not CONTROL_HOLDER_ROLE:
        raise WsError(
            f"role {role.value!r} may not send control frame {frame_type.value!r}; "
            f"command authority is held only by {CONTROL_HOLDER_ROLE.value!r}"
        )


# ---------------------------------------------------------------------------
# Backpressure — bufferedAmount protects the lease, drops the camera (HOL, ⑦)
# ---------------------------------------------------------------------------

# The WS send-buffer level (`bufferedAmount`) past which the backend sheds load.
# Above it, camera frames are dropped and the lease/command/telemetry classes are
# protected, so a saturated link never delays a dead-man renewal (FR-GUI-042 H2).
BUFFERED_AMOUNT_THRESHOLD_BYTES = 1 << 20

# The frame types dropped first under backpressure, and the ones always protected.
BACKPRESSURE_DROP_FRAMES = (WsFrameType.CAMERA,)
BACKPRESSURE_PROTECTED_FRAMES = (
    WsFrameType.LEASE_RENEW,
    WsFrameType.LEASE_GRANT,
    WsFrameType.LEASE_REJECT,
    WsFrameType.STOP_HOLD,
    WsFrameType.COMMAND,
    WsFrameType.TELEMETRY,
)


def should_drop_under_backpressure(frame_type: WsFrameType, buffered_amount: int) -> bool:
    """Whether a frame is shed at a given send-buffer level.

    Only camera frames are shed, and only once the buffer is over threshold; the
    lease, command and telemetry classes are never dropped, so head-of-line pressure
    from a camera flood cannot delay a renewal.

    Args:
        frame_type: The frame competing for the link.
        buffered_amount: The current WS send-buffer level in bytes.

    Returns:
        (bool) True only for a camera frame above the backpressure threshold.
    """
    return (
        frame_type in BACKPRESSURE_DROP_FRAMES and buffered_amount > BUFFERED_AMOUNT_THRESHOLD_BYTES
    )


# ---------------------------------------------------------------------------
# Security — WSS/TLS, Origin allowlist, no plaintext, no wildcard (⑦, FR-OPS-090)
# ---------------------------------------------------------------------------

WS_SECURE_SCHEME = "wss"
WS_PLAINTEXT_SCHEME = "ws"
WILDCARD_ORIGIN = "*"


@dataclass(frozen=True)
class WsSecurityPolicy:
    """The control channel's transport-security requirements (FR-GUI-092 H3).

    The channel is served over WSS/TLS with an Origin allowlist; plaintext `ws://`
    and a wildcard Origin are refused. CSRF/CORS defence is required for the paired
    REST surface.

    Attributes:
        scheme: The WS URL scheme; must be `wss`.
        origin_allowlist: The exact Origins permitted; must be non-empty and must
            not contain the wildcard.
        csrf_cors_enforced: Whether CSRF/CORS defence is enforced.
    """

    scheme: str
    origin_allowlist: tuple[str, ...]
    csrf_cors_enforced: bool

    def __post_init__(self) -> None:
        """Reject a plaintext scheme, a wildcard Origin, or missing CSRF/CORS."""
        if self.scheme != WS_SECURE_SCHEME:
            raise WsError(
                f"WS scheme must be {WS_SECURE_SCHEME!r} (WSS/TLS); {self.scheme!r} is refused"
            )
        if not self.origin_allowlist:
            raise WsError("an Origin allowlist is required; an empty allowlist admits any Origin")
        if WILDCARD_ORIGIN in self.origin_allowlist:
            raise WsError("a wildcard Origin is forbidden; the allowlist must name exact Origins")
        if not self.csrf_cors_enforced:
            raise WsError("CSRF/CORS defence is required on the control channel")


# ---------------------------------------------------------------------------
# Public health — must not leak the control holder or the active profile (⑧)
# ---------------------------------------------------------------------------

# The fields a public health payload must never carry: a leak would tell an
# unauthenticated caller who holds control and what profile is live (FR-GUI-092).
PUBLIC_HEALTH_FORBIDDEN_FIELDS = ("control_holder", "active_profile")


def health_leaks(payload: dict[str, object]) -> tuple[str, ...]:
    """Return the forbidden fields a health payload leaks, if any.

    Args:
        payload: A candidate public health payload.

    Returns:
        (tuple[str, ...]) The forbidden field names present, in declared order.
    """
    return tuple(field for field in PUBLIC_HEALTH_FORBIDDEN_FIELDS if field in payload)


def public_health(payload: dict[str, object]) -> dict[str, object]:
    """Project a health payload to its public form, stripping the forbidden fields.

    Args:
        payload: The internal health payload.

    Returns:
        (dict[str, object]) The payload with control-holder and active-profile removed.
    """
    return {
        key: value for key, value in payload.items() if key not in PUBLIC_HEALTH_FORBIDDEN_FIELDS
    }


# ---------------------------------------------------------------------------
# The frozen body — generated from this typed surface (single source)
# ---------------------------------------------------------------------------

# The camera frame carries the CTR-PRIM camera-identifier join as its tag; named
# here so the generated body records the exact separator the primitive owns.
_CAMERA_TAG_TEMPLATE = f"<slot>{WS_TAG_SEPARATOR}<channel>"


def _frame_body(spec: FrameSpec) -> dict[str, Any]:
    """Render one frame row of the frozen body from its `FrameSpec`."""
    body: dict[str, Any] = {
        "direction": spec.direction.value,
        "payload": spec.payload.value,
        "queue": spec.queue.name,
        "priority": int(spec.priority),
        "control_frame": spec.is_control_frame,
        "fields": list(spec.fields),
    }
    if spec.frame_type is WsFrameType.CAMERA:
        body["tag"] = _CAMERA_TAG_TEMPLATE
        body["tag_separator"] = WS_TAG_SEPARATOR
    return body


def canonical_envelope() -> dict[str, Any]:
    """Build the frozen envelope body from this typed surface and `CTR-PRIM@v1`.

    The frozen `contracts/ws/envelope.schema.json` body (`CONTRACT_FROZEN`, frozen by
    `WP-3A-06`) is a pure projection of this module: every frame type, priority,
    lease field and security rule is read from the Python declarations, so the JSON
    body and the typed mirror cannot diverge by construction. `WP-3A-06` writes
    `envelope_json()` to the frozen path and locks its content hash.

    Returns:
        (dict[str, Any]) The canonical envelope body, in stable declaration order.
    """
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": f"https://openarm/contracts/{CONTRACT_ID}",
        "contract": CONTRACT_ID,
        "title": CONTRACT_TITLE,
        "description": CONTRACT_DESCRIPTION,
        "schema_version": SCHEMA_VERSION,
        "consumed_contracts": list(CONSUMED_CONTRACTS),
        "transport": {
            "realtime_channel": REALTIME_CHANNEL,
            "single_realtime_channel": True,
            "forbidden_parallel_stacks": list(FORBIDDEN_PARALLEL_STACKS),
            "grpc_scope": "backend-remote-inference-only",
        },
        "frame_directions": [direction.value for direction in FrameDirection],
        "frame_types": {frame.value: _frame_body(FRAME_TABLE[frame]) for frame in WsFrameType},
        "lease": {
            "canon": "backend.deadman (WP-2A-02)",
            "expiry_field": LEASE_EXPIRY_FIELD,
            "issued_field": LEASE_ISSUED_FIELD,
            "generation_field": LEASE_GENERATION_FIELD,
            "generation_field_maps_to_canon": LEASE_GENERATION_CANON_FIELD,
            "sequence_field": LEASE_SEQUENCE_FIELD,
            "session_field": LEASE_SESSION_FIELD,
            "expiry_judge_role": EXPIRY_JUDGE_ROLE.value,
            "client_frame_carries_no_expiry": client_frames_omit_expiry(),
            "age_filter": {
                "max_lease_age_field": MAX_LEASE_AGE_FIELD,
                "age_input_role": ClockRole.CLIENT.value,
            },
            "reject_reasons": [reason.value for reason in LeaseRejectReason],
            "rearm_handshake": {"frames": [frame.value for frame in REARM_HANDSHAKE_FRAMES]},
        },
        "queues": {
            "priority_classes": {member.name.lower(): int(member) for member in PriorityClass},
            "lease_is_highest_priority": min(PriorityClass) is PriorityClass.LEASE,
            "bindings": {frame.value: FRAME_TABLE[frame].queue.name for frame in WsFrameType},
        },
        "backpressure": {
            "signal": "bufferedAmount",
            "threshold_bytes": BUFFERED_AMOUNT_THRESHOLD_BYTES,
            "drop_on_exceed": [frame.value for frame in BACKPRESSURE_DROP_FRAMES],
            "protected_frames": [frame.value for frame in BACKPRESSURE_PROTECTED_FRAMES],
        },
        "security": {
            "scheme": WS_SECURE_SCHEME,
            "plaintext_scheme_forbidden": WS_PLAINTEXT_SCHEME,
            "origin_allowlist_required": True,
            "wildcard_origin_forbidden": True,
            "csrf_cors_required": True,
        },
        "roles": {
            "values": [role.value for role in WsRole],
            "control_holder_role": CONTROL_HOLDER_ROLE.value,
            "observer_may_send_control_frame": False,
            "single_control_authority": True,
        },
        "health": {
            "public": True,
            "forbidden_fields": list(PUBLIC_HEALTH_FORBIDDEN_FIELDS),
        },
    }


def envelope_json() -> str:
    """Serialise the frozen body to the exact bytes `WP-3A-06` freezes.

    Returns:
        (str) The canonical envelope as pretty JSON with a trailing newline.
    """
    return json.dumps(canonical_envelope(), indent=2, ensure_ascii=False) + "\n"


__all__ = [
    "BACKPRESSURE_DROP_FRAMES",
    "BACKPRESSURE_PROTECTED_FRAMES",
    "BUFFERED_AMOUNT_THRESHOLD_BYTES",
    "CLIENT_LEASE_FRAMES",
    "CONSUMED_CONTRACTS",
    "CONTRACT_DESCRIPTION",
    "CONTRACT_ID",
    "CONTRACT_TITLE",
    "CONTROL_HOLDER_ROLE",
    "FORBIDDEN_PARALLEL_STACKS",
    "FRAME_TABLE",
    "LEASE_GENERATION_CANON_FIELD",
    "LEASE_GENERATION_FIELD",
    "LEASE_REASON_FIELD",
    "LEASE_SEQUENCE_FIELD",
    "LEASE_SESSION_FIELD",
    "MAX_LEASE_AGE_FIELD",
    "PUBLIC_HEALTH_FORBIDDEN_FIELDS",
    "REALTIME_CHANNEL",
    "REARM_HANDSHAKE_FRAMES",
    "SCHEMA_VERSION",
    "WS_PLAINTEXT_SCHEME",
    "WS_SECURE_SCHEME",
    "WILDCARD_ORIGIN",
    "FrameDirection",
    "FramePayload",
    "FrameSpec",
    "LeaseRejectReason",
    "WsError",
    "WsFrameType",
    "WsRole",
    "WsSecurityPolicy",
    "assert_expiry_owner_is_server",
    "authorize_send",
    "camera_frame_tag",
    "canonical_envelope",
    "client_frames_omit_expiry",
    "envelope_json",
    "health_leaks",
    "public_health",
    "should_drop_under_backpressure",
    "slot_from_camera_frame_tag",
]
