"""CTR-PRIM@v1 — the single definition point of the six shared 3A primitives.

`02b` §5.0b establishes the invariant this module exists to hold: the five 3A
schemas (`CTR-CAM`/`CAP`/`TEL`/`WS`/`REC`) do not merely resemble one another,
they *share* six primitives, and a primitive defined five times is five
primitives. Each of the six is defined here exactly once; `CTR-CAM@v1`..
`CTR-REC@v1` consume these definitions by import and must never restate one. A
consumer that declares its own camera-identifier grammar, or its own timestamp
domain, has split the contract — the `FAIL_BLOCKING` defect 3B would amplify
thirteen ways (`02b` §5.2 WP-3A-00 negative branch).

The six primitives, and the one rule each carries that a consumer must not bend:

1. Camera identifier — one slot-key grammar. The same key must round-trip-join
   across the CAM registry key, the CAP sidecar column, the WS binary frame tag,
   and the REC `observation.images.<slot>` key, or preview, sidecar and dataset
   stop joining (`02b` §5.0b row 1).
2. Timestamp domain — `CLOCK_MONOTONIC` nanoseconds, and the expiry-judge clock
   is the SERVER's, pinned here (`EXPIRY_JUDGE_ROLE`). The client clock is an age
   input only. `CTR-WS@v1` transports the lease; it does not get to move that
   ownership (`02b` §5.0b row 2, U-4). The synthetic dataset grid timestamp is a
   distinct type from a real capture timestamp so the two cannot be conflated.
3. Frame-type tag — RGB is required, depth is optional; one enum for both, so a
   depth stream's channel meaning is the same in CAM capability, WS channel tag
   and REC feature key (`02b` §5.0b row 3).
4. Action payload shape — position-only, 8 single-arm / 16 bimanual, unit-tagged
   in degrees. Re-exported from `CTR-ACT@v1` rather than restated, so the tele-op
   command, the WS command frame and the recorded action are one shape
   (`02b` §5.0b row 4).
5. Queue semantics — bounded, priority-classed, with a drop policy AND a drop
   *classification* (normal vs defect vs counted). Without the classification the
   same dropped frame reads as healthy in one quality report and broken in
   another (`02b` §5.0b row 5).
6. Error envelope — one wrapper around a `CTR-ERR@v1` code, so an `OA-*` code is
   surfaced identically by all five contracts (`02b` §5.0b row 6).

This module is `CONTRACT_FROZEN`: once `CTR-PRIM@v1` is frozen (`WP-3A-00`), a
byte change here is a `CI-09` freeze violation, and widening a primitive is
`CTR-PRIM@v2` with all five consuming contracts `SUPERSEDED` (`06` §4.3, `CR-2`).
It imports only the light contract lane (`contracts.action`/`errors`/`units`);
nothing here pulls the robot stack, so consumers stay in the offline lane.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum, StrEnum

from contracts.action import (
    BIMANUAL_ACTION_DIM,
    SINGLE_ARM_ACTION_DIM,
    AcceptedPositionAction,
    RequestedPositionAction,
)
from contracts.action import CONTRACT_ID as ACTION_CONTRACT_ID
from contracts.errors import CONTRACT_ID as ERROR_CONTRACT_ID
from contracts.errors import REGISTRY, ErrorCode, OaError, Severity, codes, is_valid_severity
from contracts.units import Deg

# The contract id this module is the frozen body of. Consumers key freeze checks,
# staleness and the no-redefinition scan on this exact string, so it is named once.
CONTRACT_ID = "CTR-PRIM@v1"

# The frozen generation. A change to any primitive is a new generation
# (`CTR-PRIM@v2`), never an in-place edit of this literal (`06` §4.3).
SCHEMA_VERSION = 1

# The upstream frozen contracts these primitives consume by reference. Named so a
# consumer can assert it is joining against the same generations WP-3A-00 froze
# against, and so a bump of any of them propagates staleness here (`CR-2`).
CONSUMED_CONTRACTS = (ACTION_CONTRACT_ID, ERROR_CONTRACT_ID, "CTR-UNIT@v1")


class PrimitiveRedefinitionError(ValueError):
    """Raised when a value violates a frozen primitive's single-definition rule.

    The one exception every primitive shares: a consumer that tries to restate a
    primitive — a bad camera key, a non-SERVER expiry owner — is refused here
    rather than allowed to fork the contract (`02b` §5.2 WP-3A-00).
    """


# ---------------------------------------------------------------------------
# Primitive 1 — camera identifier (slot-key grammar)
# ---------------------------------------------------------------------------

# A slot key is a lowercase snake token. The grammar is deliberately narrow: the
# same string is a Python dict key (CAM), a parquet column stem (CAP), a WS frame
# tag (WS) and a LeRobot feature-key segment (REC), and only `[a-z][a-z0-9_]*`
# is safe in all four without escaping.
CAMERA_SLOT_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

# Per-arm cameras carry an arm prefix; a top-level camera carries none. The
# prefix is part of the key, not metadata beside it, so the arm a frame belongs
# to survives every join (`02b` §5.1 WP-3A-01: `left_`/`right_` auto-attached).
ARM_SIDES = ("left", "right")
ARM_PREFIXES = {"left": "left_", "right": "right_"}

# Simulation scene cameras live in their own namespace so a sim-only camera can
# never collide with, or be joined to, a real slot (`02b` §5.1 WP-3A-01 ⑤).
SIM_NAMESPACE_PREFIX = "sim_"

# The join derivations. Each consuming contract renders the slot into its own
# surface through exactly one of these, and parses it back through the inverse,
# which is what makes the four surfaces one identifier.
IMAGE_KEY_PREFIX = "observation.images."
CAPTURE_TS_COLUMN_SUFFIX = "_capture_ts"
DEPTH_KEY_SUFFIX = "_depth"
WS_TAG_SEPARATOR = ":"


@dataclass(frozen=True)
class CameraSlotKey:
    """A camera identifier: one validated slot key shared by all four contracts.

    The value is the identifier itself. `arm` and `is_sim` are derived from the
    key, never stored beside it, so there is no second place they could disagree
    with the string.

    Attributes:
        value: The slot key, matching `CAMERA_SLOT_KEY_PATTERN`.
    """

    value: str

    def __post_init__(self) -> None:
        """Reject any string outside the one slot-key grammar."""
        if not CAMERA_SLOT_KEY_PATTERN.match(self.value):
            raise PrimitiveRedefinitionError(
                f"camera slot key {self.value!r} violates the {CONTRACT_ID} grammar "
                f"{CAMERA_SLOT_KEY_PATTERN.pattern}"
            )

    @property
    def is_sim(self) -> bool:
        """Whether this is a simulation-namespace scene camera."""
        return self.value.startswith(SIM_NAMESPACE_PREFIX)

    @property
    def arm(self) -> str | None:
        """The arm this camera is bound to (`left`/`right`), or None if top-level."""
        for side, prefix in ARM_PREFIXES.items():
            if self.value.startswith(prefix):
                return side
        return None

    def image_key(self) -> str:
        """The REC `observation.images.<slot>` RGB feature key for this slot."""
        return f"{IMAGE_KEY_PREFIX}{self.value}"

    def depth_key(self) -> str:
        """The REC depth feature key (`<slot>_depth`) for this slot."""
        return f"{IMAGE_KEY_PREFIX}{self.value}{DEPTH_KEY_SUFFIX}"

    def capture_ts_column(self) -> str:
        """The CAP sidecar column (`<slot>_capture_ts`) carrying this slot's grab time."""
        return f"{self.value}{CAPTURE_TS_COLUMN_SUFFIX}"

    def ws_tag(self, frame_type: FrameType) -> str:
        """The WS binary frame tag (`<slot>:<channel>`) for this slot and channel."""
        return f"{self.value}{WS_TAG_SEPARATOR}{frame_type.value}"


def arm_slot(side: str, base: str) -> CameraSlotKey:
    """Build a per-arm slot key by auto-attaching the arm prefix (`02b` §5.1).

    Args:
        side: `"left"` or `"right"`.
        base: The bare camera name, without any arm prefix.

    Returns:
        (CameraSlotKey) The prefixed, validated slot key.

    Raises:
        PrimitiveRedefinitionError: If the side is not a known arm, or the base is
            already arm/sim-prefixed (double-prefixing forks the identifier).
    """
    if side not in ARM_PREFIXES:
        raise PrimitiveRedefinitionError(f"unknown arm side {side!r}; expected one of {ARM_SIDES}")
    if base.startswith((*ARM_PREFIXES.values(), SIM_NAMESPACE_PREFIX)):
        raise PrimitiveRedefinitionError(f"base {base!r} is already namespaced; pass the bare name")
    return CameraSlotKey(f"{ARM_PREFIXES[side]}{base}")


def sim_slot(base: str) -> CameraSlotKey:
    """Build a simulation scene-camera slot key in the sim namespace.

    Args:
        base: The bare scene-camera name, without any namespace prefix.

    Returns:
        (CameraSlotKey) The sim-namespaced, validated slot key.
    """
    if base.startswith(SIM_NAMESPACE_PREFIX):
        raise PrimitiveRedefinitionError(f"base {base!r} is already sim-namespaced")
    return CameraSlotKey(f"{SIM_NAMESPACE_PREFIX}{base}")


def slot_from_image_key(image_key: str) -> CameraSlotKey:
    """Recover the slot key from a REC `observation.images.<slot>` key.

    Args:
        image_key: A dataset image feature key.

    Returns:
        (CameraSlotKey) The slot the key was derived from.

    Raises:
        PrimitiveRedefinitionError: If the key does not carry the image prefix.
    """
    if not image_key.startswith(IMAGE_KEY_PREFIX):
        raise PrimitiveRedefinitionError(f"{image_key!r} is not an {IMAGE_KEY_PREFIX}* key")
    return CameraSlotKey(image_key[len(IMAGE_KEY_PREFIX) :])


def slot_from_capture_ts_column(column: str) -> CameraSlotKey:
    """Recover the slot key from a CAP `<slot>_capture_ts` sidecar column.

    Args:
        column: A capture-timestamp sidecar column name.

    Returns:
        (CameraSlotKey) The slot the column was derived from.

    Raises:
        PrimitiveRedefinitionError: If the column does not carry the capture-ts suffix.
    """
    if not column.endswith(CAPTURE_TS_COLUMN_SUFFIX):
        raise PrimitiveRedefinitionError(f"{column!r} is not a *{CAPTURE_TS_COLUMN_SUFFIX} column")
    return CameraSlotKey(column[: -len(CAPTURE_TS_COLUMN_SUFFIX)])


def slot_from_ws_tag(tag: str) -> CameraSlotKey:
    """Recover the slot key from a WS `<slot>:<channel>` binary frame tag.

    Args:
        tag: A WS binary frame tag.

    Returns:
        (CameraSlotKey) The slot the tag carries.

    Raises:
        PrimitiveRedefinitionError: If the tag carries no channel separator.
    """
    if WS_TAG_SEPARATOR not in tag:
        raise PrimitiveRedefinitionError(f"{tag!r} carries no {WS_TAG_SEPARATOR}<channel> tag")
    return CameraSlotKey(tag.split(WS_TAG_SEPARATOR, 1)[0])


# ---------------------------------------------------------------------------
# Primitive 2 — timestamp domain
# ---------------------------------------------------------------------------

# All monotonic timestamps in the system are `CLOCK_MONOTONIC` nanoseconds. Named
# once so a consumer states the clock source by reference, never by re-declaring
# its own (`02b` §5.0b row 2).
CLOCK_SOURCE = "CLOCK_MONOTONIC"
TIMESTAMP_UNIT_NS = "ns"


class ClockRole(StrEnum):
    """Which participant's clock a monotonic timestamp was read on.

    Server and client monotonic clocks are unrelated epochs; a value from one is
    never comparable to a value from the other. The role is the contract that
    keeps them apart (`02b` §5.0b row 2, U-4).
    """

    SERVER = "server"
    CLIENT = "client"


# The pin (`02b` §5.2 WP-3A-00 ③): lease expiry is judged on the SERVER clock and
# only the SERVER clock. `CTR-WS@v1` carries the lease but cannot move this
# ownership; `verify_expiry_owner` refuses any other role.
EXPIRY_JUDGE_ROLE = ClockRole.SERVER

# The client clock is an *age input* only — how old the client believes its last
# lease is — never the authority on whether it expired (U-4 dead-man design).
AGE_INPUT_ROLE = ClockRole.CLIENT

# The lease field names the WS envelope transports. The expiry field is on the
# server clock (the judge); the issued field is on the client clock (age input).
# Named here so the WS schema references them rather than inventing field names
# whose clock ownership is then ambiguous.
LEASE_EXPIRY_FIELD = "expiry_mono_server"
LEASE_ISSUED_FIELD = "issued_mono_client"


class TimestampDomain(StrEnum):
    """The two orthogonal meanings a dataset time value can carry.

    A real capture time and a synthetic playback grid are different quantities
    that happen to both be "a timestamp"; typing them apart stops a consumer from
    reading one as the other (`02b` §5.0b row 2: grid `timestamp` ⟂ `capture_ts`).
    """

    CAPTURE = "capture"
    SYNTHETIC_GRID = "synthetic_grid"


@dataclass(frozen=True)
class CaptureTimestamp:
    """A real frame-capture instant: monotonic nanoseconds attached at grab time.

    This is the CAP primitive's payload (`02b` §5.1 WP-3A-02: attached immediately
    after grab, never by a downstream consumer at receive time).

    Attributes:
        mono_ns: `CLOCK_MONOTONIC` nanoseconds read at the grab point.
    """

    mono_ns: int

    def __post_init__(self) -> None:
        """Reject a non-integer nanosecond count."""
        if not isinstance(self.mono_ns, int) or isinstance(self.mono_ns, bool):
            raise PrimitiveRedefinitionError(f"{CLOCK_SOURCE} timestamp must be int ns")

    @property
    def domain(self) -> TimestampDomain:
        """This value's domain — always a real capture instant."""
        return TimestampDomain.CAPTURE


@dataclass(frozen=True)
class SyntheticGridTimestamp:
    """The LeRobot dataset `timestamp` = `frame_index / fps`: a synthetic grid.

    Deliberately NOT a `CaptureTimestamp`. It is a playback-grid coordinate in
    seconds, orthogonal to when the frame was actually captured, and the UI/meta
    must present it as synthetic (`02b` §5.1 WP-3A-02, `02b` §5.2 WP-3A-02 ④).

    Attributes:
        seconds: `frame_index / fps`, the synthetic grid position in seconds.
    """

    seconds: float

    @property
    def domain(self) -> TimestampDomain:
        """This value's domain — always the synthetic playback grid."""
        return TimestampDomain.SYNTHETIC_GRID


def verify_expiry_owner(declared: ClockRole) -> None:
    """Enforce the primitive-level pin that only the SERVER clock judges expiry.

    This is the mechanism behind `02b` §5.2 WP-3A-00 ③: a downstream contract
    (notably `CTR-WS@v1`) that declares any other expiry-judge role is refused
    here, so it cannot override an ownership fixed at the primitive level.

    Args:
        declared: The expiry-judge clock role a consuming contract declares.

    Raises:
        PrimitiveRedefinitionError: If `declared` is not `EXPIRY_JUDGE_ROLE`.
    """
    if declared != EXPIRY_JUDGE_ROLE:
        raise PrimitiveRedefinitionError(
            f"expiry judge is pinned to {EXPIRY_JUDGE_ROLE.value} at the {CONTRACT_ID} level; "
            f"a contract cannot re-own it as {declared.value}"
        )


# ---------------------------------------------------------------------------
# Primitive 3 — frame-type tag
# ---------------------------------------------------------------------------


class FrameType(StrEnum):
    """The image channel kinds a camera can carry (`02b` §5.0b row 3).

    One enum for CAM capability, WS binary channel tag and REC feature key, so a
    depth channel means the same thing at every surface.
    """

    RGB = "rgb"
    DEPTH = "depth"


# RGB is a mandatory capability; depth is optional (`02b` §5.1 WP-3A-01: RGB
# required, depth optional). A CAM registry that requires depth of every camera
# has redefined the capability floor and is rejected downstream.
REQUIRED_FRAME_TYPE = FrameType.RGB
OPTIONAL_FRAME_TYPES = (FrameType.DEPTH,)

# The fixed channel count and element type per frame kind. Depth is single-channel
# uint16 millimetres with 0 = "no measurement" (`02b` §6.1 WP-3B-03); RGB is
# three-channel uint8. Consumers read these, never re-declare them.
FRAME_TYPE_CHANNELS = {FrameType.RGB: 3, FrameType.DEPTH: 1}
FRAME_TYPE_DTYPE = {FrameType.RGB: "uint8", FrameType.DEPTH: "uint16"}


# ---------------------------------------------------------------------------
# Primitive 4 — action payload shape (re-export of CTR-ACT@v1)
# ---------------------------------------------------------------------------

# The action is position-only, unit-tagged in degrees. The shape lives in
# `CTR-ACT@v1`; it is re-exported, not restated, so the tele-op command, the WS
# command frame and the recorded action are provably one shape (`02b` §5.0b
# row 4). `.vel`/`.torque` are never action dimensions (`02b` §5.2 WP-3A-05).
ACTION_IS_POSITION_ONLY = True
ACTION_POSITION_UNIT = "deg"

# The action shape itself (`SINGLE_ARM_ACTION_DIM`, `BIMANUAL_ACTION_DIM`,
# `AcceptedPositionAction`, `RequestedPositionAction`, `Deg`) is re-exported from
# `CTR-ACT@v1`/`CTR-UNIT@v1` through this module's `__all__`, so a consumer imports
# it from the single primitive point rather than reaching into `contracts.action`.


# ---------------------------------------------------------------------------
# Primitive 5 — queue semantics
# ---------------------------------------------------------------------------


class DropPolicy(StrEnum):
    """How a bounded queue sheds load when full (`02b` §5.0b row 5)."""

    LATEST_WINS = "latest_wins"
    DROP_OLDEST = "drop_oldest"
    BLOCK = "block"


class DropClassification(StrEnum):
    """What a drop *means* for the quality report — the missing half of `02b` §5.0b.

    A drop policy alone leaves "was this drop healthy or a fault" undefined, so
    the same dropped frame reads three ways across three reports. This fixes the
    meaning per queue class.
    """

    NORMAL = "normal"
    DEFECT = "defect"
    COUNTED = "counted"


class PriorityClass(IntEnum):
    """WS delivery priority; lower value is served first (`02b` §5.2 WP-3A-04 ②).

    The lease frame outranks every other class so a camera flood cannot delay a
    dead-man renewal — the head-of-line mitigation the single-WS design rests on.
    """

    LEASE = 0
    COMMAND = 1
    TELEMETRY = 2
    CAMERA = 3


@dataclass(frozen=True)
class QueueSemantics:
    """One bounded queue class: its capacity, priority, drop policy and meaning.

    Attributes:
        name: The queue-class name (a `QUEUE_PROFILES` key).
        bounded_capacity: Maximum queued items; the queue is always bounded.
        priority: Delivery priority class (lease first).
        drop_policy: How the queue sheds load when full.
        drop_classification: Whether a drop from this class is normal, a defect,
            or merely counted — the single answer the quality report reads.
    """

    name: str
    bounded_capacity: int
    priority: PriorityClass
    drop_policy: DropPolicy
    drop_classification: DropClassification

    def __post_init__(self) -> None:
        """Reject an unbounded capacity — every queue class is bounded by contract."""
        if self.bounded_capacity <= 0:
            raise PrimitiveRedefinitionError(
                f"queue {self.name!r} must be bounded (capacity > 0), got {self.bounded_capacity}"
            )


# The named queue classes every WS/CAM/CAP consumer shares. A lease drop is a
# DEFECT (the dead-man must never lose a renewal); a preview drop is NORMAL
# (latest-wins by design); a capture-match miss is COUNTED (expected, but the
# quality report counts it). Capacities are the frozen defaults.
QUEUE_PROFILES = {
    "lease": QueueSemantics(
        name="lease",
        bounded_capacity=1,
        priority=PriorityClass.LEASE,
        drop_policy=DropPolicy.LATEST_WINS,
        drop_classification=DropClassification.DEFECT,
    ),
    "command": QueueSemantics(
        name="command",
        bounded_capacity=8,
        priority=PriorityClass.COMMAND,
        drop_policy=DropPolicy.DROP_OLDEST,
        drop_classification=DropClassification.COUNTED,
    ),
    "telemetry": QueueSemantics(
        name="telemetry",
        bounded_capacity=16,
        priority=PriorityClass.TELEMETRY,
        drop_policy=DropPolicy.LATEST_WINS,
        drop_classification=DropClassification.NORMAL,
    ),
    "camera_preview": QueueSemantics(
        name="camera_preview",
        bounded_capacity=1,
        priority=PriorityClass.CAMERA,
        drop_policy=DropPolicy.LATEST_WINS,
        drop_classification=DropClassification.NORMAL,
    ),
    "capture_match": QueueSemantics(
        name="capture_match",
        bounded_capacity=4,
        priority=PriorityClass.CAMERA,
        drop_policy=DropPolicy.DROP_OLDEST,
        drop_classification=DropClassification.COUNTED,
    ),
}


# ---------------------------------------------------------------------------
# Primitive 6 — error envelope (wrapping CTR-ERR@v1)
# ---------------------------------------------------------------------------

# The canonical shape of an `OA-*` code as an error string. Named once so the
# envelope validates a code by the same pattern the error registry uses, without
# re-declaring the code grammar.
ERROR_CODE_PATTERN = re.compile(r"^OA-[A-Z]+-[0-9A-F]{3}$")


@dataclass(frozen=True)
class ErrorEnvelope:
    """One `CTR-ERR@v1` error, wrapped identically for all five contracts.

    The envelope is the single shape a CAM/CAP/TEL/WS/REC surface reports an error
    in (`02b` §5.0b row 6): a registered `OA-*` code, a human reason, and the
    code's fixed severity. It never invents a code — `code` must match a row in
    the frozen `CTR-ERR@v1` registry.

    Attributes:
        code: A registered `OA-*` code string.
        reason: The human-readable reason this error was raised.
        severity: The `CTR-ERR@v1` severity level.
    """

    code: str
    reason: str
    severity: Severity

    def __post_init__(self) -> None:
        """Reject a malformed code or an out-of-domain severity."""
        if not ERROR_CODE_PATTERN.match(self.code):
            raise PrimitiveRedefinitionError(f"error code {self.code!r} is not an OA-* code")
        if not is_valid_severity(self.severity):
            raise PrimitiveRedefinitionError(f"severity {self.severity!r} is outside CTR-ERR@v1")


def error_envelope(code: ErrorCode, reason: str) -> ErrorEnvelope:
    """Wrap a registered `CTR-ERR@v1` code in the shared error envelope.

    Args:
        code: A code from the frozen registry (`contracts.errors.codes`).
        reason: The human-readable reason to attach.

    Returns:
        (ErrorEnvelope) The envelope carrying the code, reason and its severity.
    """
    return ErrorEnvelope(code=code.code, reason=reason, severity=code.severity)


# ---------------------------------------------------------------------------
# The single-definition guard surface
# ---------------------------------------------------------------------------

# The names a consuming 3A schema (`CTR-CAM`..`CTR-REC`) must obtain by importing
# from `contracts.prim`, and must never bind with its own class/assignment. The
# no-redefinition checker (`contracts.prim.redefinition`) reads this set; a
# consumer that defines any of these has forked a primitive (`02b` §5.2 WP-3A-00
# ②: "CAP declaring its own timestamp domain fails").
RESERVED_PRIMITIVE_SYMBOLS = frozenset(
    {
        "CameraSlotKey",
        "CAMERA_SLOT_KEY_PATTERN",
        "ARM_PREFIXES",
        "SIM_NAMESPACE_PREFIX",
        "ClockRole",
        "CLOCK_SOURCE",
        "EXPIRY_JUDGE_ROLE",
        "TimestampDomain",
        "CaptureTimestamp",
        "SyntheticGridTimestamp",
        "FrameType",
        "FRAME_TYPE_CHANNELS",
        "DropPolicy",
        "DropClassification",
        "PriorityClass",
        "QueueSemantics",
        "ErrorEnvelope",
    }
)

__all__ = [
    "ACTION_CONTRACT_ID",
    "ACTION_IS_POSITION_ONLY",
    "ACTION_POSITION_UNIT",
    "AGE_INPUT_ROLE",
    "ARM_PREFIXES",
    "ARM_SIDES",
    "BIMANUAL_ACTION_DIM",
    "CAMERA_SLOT_KEY_PATTERN",
    "CAPTURE_TS_COLUMN_SUFFIX",
    "CLOCK_SOURCE",
    "CONSUMED_CONTRACTS",
    "CONTRACT_ID",
    "DEPTH_KEY_SUFFIX",
    "ERROR_CODE_PATTERN",
    "ERROR_CONTRACT_ID",
    "EXPIRY_JUDGE_ROLE",
    "FRAME_TYPE_CHANNELS",
    "FRAME_TYPE_DTYPE",
    "IMAGE_KEY_PREFIX",
    "LEASE_EXPIRY_FIELD",
    "LEASE_ISSUED_FIELD",
    "OPTIONAL_FRAME_TYPES",
    "QUEUE_PROFILES",
    "REGISTRY",
    "REQUIRED_FRAME_TYPE",
    "RESERVED_PRIMITIVE_SYMBOLS",
    "SCHEMA_VERSION",
    "SIM_NAMESPACE_PREFIX",
    "SINGLE_ARM_ACTION_DIM",
    "TIMESTAMP_UNIT_NS",
    "WS_TAG_SEPARATOR",
    "AcceptedPositionAction",
    "CameraSlotKey",
    "CaptureTimestamp",
    "ClockRole",
    "Deg",
    "DropClassification",
    "DropPolicy",
    "ErrorCode",
    "ErrorEnvelope",
    "FrameType",
    "OaError",
    "PriorityClass",
    "PrimitiveRedefinitionError",
    "QueueSemantics",
    "RequestedPositionAction",
    "Severity",
    "SyntheticGridTimestamp",
    "TimestampDomain",
    "arm_slot",
    "codes",
    "error_envelope",
    "is_valid_severity",
    "sim_slot",
    "slot_from_capture_ts_column",
    "slot_from_image_key",
    "slot_from_ws_tag",
    "verify_expiry_owner",
]
