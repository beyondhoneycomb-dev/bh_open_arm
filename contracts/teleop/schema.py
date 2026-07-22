"""CTR-TEL@v1 — the teleoperator plugin contract, a CTR-PRIM@v1 consumer.

`02b` §5.2 WP-3A-03: the teleoperator is a LeRobot **unmodified plugin**, never a
fork. It consumes three of the six shared primitives from `CTR-PRIM@v1` by import
and must not restate any of them (`02b` §5.0b):

- **action payload shape** — position-only, 8 single-arm / 16 bimanual. The `.pos`
  keys of `get_action()` carry the IK solution in degrees; the dataset action
  keyset is flat `{key: type}` (`FR-TEL-004`), and `.vel`/`.torque` keys ride along
  as honest zeros because `send_action` hardcodes them (`05` §2.5, `FR-TEL-064`).
- **timestamp domain** — the VR source `t` is the CLIENT clock (an age input, never
  the authority) and the PC receive instant is the SERVER `CLOCK_MONOTONIC`; both
  are preserved (`05` §2.7, `WP-3B-07`). The ownership pin is `CTR-PRIM@v1`'s.
- **error envelope** — link-loss, STALE and INVALID tracking surface through the one
  `CTR-ERR@v1`-wrapping envelope, keyed on the frozen `OA-TEL-*` codes.

The contract also fixes what the plugin must be, independent of the primitives:
`get_action()` is NON-BLOCKING (`FR-TEL-005`), a non-abstract `sync_state(obs)` is
added so the operational GUI loop is closed-loop while the LeRobot CLI path is
verification-only and open-loop (`FR-TEL-006`/`007`), tracking validity is the
three-level `OK`/`STALE`/`INVALID` model (`05` §2.7), and a KER insertion slot is
reserved that consumes zero CAN channels (`FR-TEL-062`..`064`/`066`).

This module imports only `contracts.prim` and the standard library, so it stays in
the AI-offline light lane. It is the source of the frozen body: `WP-3A-06` renders
`contracts/teleop/schema.json` from it (`contracts.teleop.reverify`) and freezes
`CTR-TEL@v1`; until then the contract is DRAFT and nothing here is on the freeze
ledger. Widening any primitive is `CTR-PRIM@v2` with `CTR-TEL@v1` SUPERSEDED, not an
edit here (`06` §4.3).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum, StrEnum

from contracts.prim import (
    AGE_INPUT_ROLE,
    BIMANUAL_ACTION_DIM,
    CLOCK_SOURCE,
    REGISTRY,
    SINGLE_ARM_ACTION_DIM,
    ClockRole,
    ErrorCode,
    ErrorEnvelope,
    codes,
    error_envelope,
)

# The contract id this module is the frozen body of. The freeze lock, staleness and
# the no-redefinition scan key on this exact string, so it is named once.
CONTRACT_ID = "CTR-TEL@v1"

# The frozen generation. A primitive change is a new generation, never an edit of
# this literal (`06` §4.3).
SCHEMA_VERSION = 1

# The one upstream contract this schema consumes by reference. The action payload
# shape, timestamp domain and error envelope all arrive through `contracts.prim`, so
# a staleness bump of `CTR-PRIM@v1` propagates here (`CR-2`).
CONSUMED_CONTRACTS = ("CTR-PRIM@v1",)


# ---------------------------------------------------------------------------
# Acceptance ① — LeRobot unmodified plugin: registration and discovery
# ---------------------------------------------------------------------------

# `register_third_party_plugins()` (lerobot `utils/import_utils.py`) auto-imports a
# distribution only when its name starts with this prefix; a name outside it is never
# discovered, so its `@register_subclass` never runs and `--teleop.type` cannot select
# it (`05` §2.3, `FR-TEL-001`). Stated here as the LeRobot fact this contract binds to,
# not as a `CTR-PRIM` primitive.
TELEOPERATOR_DIST_PREFIX = "lerobot_teleoperator_"

# The VR teleoperator's distribution, config choice, config class and device class.
# The device class name is the config class name with `Config` removed — the fallback
# `make_device_from_device_class` resolves it that way (`05` §2.3, `FR-TEL-002`).
VR_DIST_NAME = "lerobot_teleoperator_openarm_vr"
VR_TELEOP_TYPE = "openarm_vr"
VR_CONFIG_CLASS = "OpenArmVRConfig"
VR_DEVICE_CLASS = "OpenArmVR"

# The suffix `make_device_from_device_class` strips from a config class name.
CONFIG_CLASS_SUFFIX = "Config"

# The full LeRobot `Teleoperator` ABC surface a plugin must implement, unchanged in
# signature (`teleoperators/teleoperator.py`, `FR-TEL-003`). Named so a plugin can be
# checked against the complete set rather than an ad-hoc subset.
ABSTRACT_MEMBERS = frozenset(
    {
        "action_features",
        "feedback_features",
        "is_connected",
        "connect",
        "is_calibrated",
        "calibrate",
        "configure",
        "get_action",
        "send_feedback",
        "disconnect",
    }
)

# `send_feedback` is never called on the OpenArm path — the loop only feeds back to
# `unitree_g1` (`05` §2.6/§2.13) — so `feedback_features` is the empty flat mapping.
FEEDBACK_FEATURES: dict[str, type] = {}


class PluginConventionError(ValueError):
    """Raised when a teleoperator plugin breaks the LeRobot discovery convention."""


def is_plugin_convention_compliant(dist_name: str) -> bool:
    """Report whether a distribution name would be discovered by LeRobot.

    Args:
        dist_name: Candidate distribution/module name.

    Returns:
        (bool) True when the name carries the teleoperator plugin prefix.
    """
    return dist_name.startswith(TELEOPERATOR_DIST_PREFIX)


def require_plugin_convention(dist_name: str) -> None:
    """Reject a teleoperator distribution name outside the discovery convention.

    Args:
        dist_name: Candidate distribution/module name.

    Raises:
        PluginConventionError: When the name would never be auto-imported, so the
            `@register_subclass` it performs never runs and `--teleop.type` cannot
            select the plugin (acceptance ①).
    """
    if not is_plugin_convention_compliant(dist_name):
        raise PluginConventionError(
            f"distribution {dist_name!r} lacks the {TELEOPERATOR_DIST_PREFIX!r} prefix; "
            "register_third_party_plugins() would never import it and --teleop.type "
            "could not select the plugin"
        )


def device_class_from_config_class(config_class_name: str) -> str:
    """Derive the device class name LeRobot resolves from a config class name.

    Args:
        config_class_name: The `@register_subclass` config class name.

    Returns:
        (str) The device class name — the config name with the `Config` suffix removed.

    Raises:
        PluginConventionError: If the config class name does not end in `Config`, so
            the fallback resolver would look up a class that does not exist.
    """
    if not config_class_name.endswith(CONFIG_CLASS_SUFFIX):
        raise PluginConventionError(
            f"config class {config_class_name!r} must end in {CONFIG_CLASS_SUFFIX!r} for "
            "make_device_from_device_class to resolve its device class"
        )
    return config_class_name[: -len(CONFIG_CLASS_SUFFIX)]


# ---------------------------------------------------------------------------
# Acceptance ② — action_features is the flat {key: type} convention
# ---------------------------------------------------------------------------

# LeRobot carries two `action_features` conventions: (a) flat `{key: type}` and
# (b) nested `{"dtype", "shape", "names"}`. Only (a) is accepted by dataset feature
# creation; a teleoperator that emits (b) makes `aggregate_pipeline_dataset_features`
# fail (`05` §2.3, `FR-TEL-004`). These are the two convention tags this contract
# distinguishes.
FEATURE_CONVENTION_FLAT = "flat"
FEATURE_CONVENTION_NESTED = "nested"

# The keys of convention (b), any one of which marks a nested feature spec.
NESTED_FEATURE_KEYS = frozenset({"dtype", "shape", "names"})


class FeatureConventionError(ValueError):
    """Raised when action features are not the flat `{key: type}` convention."""


def feature_convention(features: Mapping[str, object]) -> str:
    """Classify an `action_features` mapping as the flat or the nested convention.

    Args:
        features: An `action_features` mapping.

    Returns:
        (str) `FEATURE_CONVENTION_FLAT` when every value is a Python type,
            `FEATURE_CONVENTION_NESTED` when a value is a nested feature spec.

    Raises:
        FeatureConventionError: When a value is neither a type nor a nested spec, so
            the mapping matches no known convention.
    """
    for key, value in features.items():
        if isinstance(value, Mapping):
            if NESTED_FEATURE_KEYS & set(value.keys()):
                return FEATURE_CONVENTION_NESTED
            raise FeatureConventionError(
                f"feature {key!r} is a mapping without any of {sorted(NESTED_FEATURE_KEYS)}"
            )
        if not isinstance(value, type):
            raise FeatureConventionError(
                f"feature {key!r} value {value!r} is neither a type (flat) nor a nested spec"
            )
    return FEATURE_CONVENTION_FLAT


def is_flat_action_features(features: Mapping[str, object]) -> bool:
    """Report whether an `action_features` mapping uses the flat convention.

    Args:
        features: An `action_features` mapping.

    Returns:
        (bool) True when the mapping is flat `{key: type}` (convention a).
    """
    return feature_convention(features) == FEATURE_CONVENTION_FLAT


def aggregate_dataset_action_features(features: Mapping[str, object]) -> dict[str, type]:
    """Emulate LeRobot dataset feature creation over an `action_features` mapping.

    This is the acceptance ② failure surface: dataset feature creation reads each
    value as a scalar Python type. The nested convention (b) supplies a mapping where
    a type is expected, which is the runtime failure a teleoperator using (b)
    reproduces — so this function raises on (b) and returns the flat dict on (a).

    Args:
        features: An `action_features` mapping.

    Returns:
        (dict[str, type]) The flat feature dict, when the mapping is convention (a).

    Raises:
        FeatureConventionError: When the mapping is the nested convention (b), the
            same failure LeRobot's `aggregate_pipeline_dataset_features` produces.
    """
    if feature_convention(features) != FEATURE_CONVENTION_FLAT:
        raise FeatureConventionError(
            "action_features uses the nested convention (b); dataset feature creation "
            "expects a scalar type per key (flat convention a) and fails on (b)"
        )
    return {key: value for key, value in features.items() if isinstance(value, type)}


# ---------------------------------------------------------------------------
# Action keyset — position-only payload consumed from CTR-PRIM, honest zeros
# ---------------------------------------------------------------------------

# The dataset action keyset carries three suffixes per motor; only `.pos` is a real
# command dimension. `.vel`/`.torque` exist because `build_dataset_frame` indexes the
# `get_action()` dict by `robot.action_features` names, so a missing key is a runtime
# `KeyError` (`05` §2.5).
POSITION_SUFFIX = ".pos"
VELOCITY_SUFFIX = ".vel"
TORQUE_SUFFIX = ".torque"

# The honest value of a non-position dimension for a VR/KER teleoperator: there is no
# torque source, and `send_action` hardcodes velocity and torque to zero (`05` §2.5,
# `FR-TEL-064`). Recording zero is the honest record of what was commanded.
ZERO_NON_POSITION_VALUE = 0.0


def position_key_count(features: Mapping[str, object]) -> int:
    """Count the position (`.pos`) dimensions in an action keyset.

    Args:
        features: An `action_features` mapping or a `get_action()` output dict.

    Returns:
        (int) Number of keys ending in `POSITION_SUFFIX`.
    """
    return sum(1 for key in features if key.endswith(POSITION_SUFFIX))


def is_action_dim_position_only(features: Mapping[str, object]) -> bool:
    """Report whether the position dimension count matches the CTR-PRIM action shape.

    The position-only width is consumed from `CTR-PRIM@v1` (`SINGLE_ARM_ACTION_DIM` /
    `BIMANUAL_ACTION_DIM`); this contract never restates it.

    Args:
        features: An `action_features` mapping or a `get_action()` output dict.

    Returns:
        (bool) True when the `.pos` count is the single-arm or bimanual action width.
    """
    return position_key_count(features) in (SINGLE_ARM_ACTION_DIM, BIMANUAL_ACTION_DIM)


def verify_non_position_dims_zero(action: Mapping[str, float]) -> None:
    """Enforce the honest-zero rule on every non-position action dimension.

    Args:
        action: A `get_action()` output dict.

    Raises:
        FeatureConventionError: If any `.vel`/`.torque` value is not zero — a VR/KER
            teleoperator has no torque source and `send_action` zeroes them, so a
            non-zero value is a fabricated command dimension (`05` §2.5).
    """
    for key, value in action.items():
        if key.endswith((VELOCITY_SUFFIX, TORQUE_SUFFIX)) and value != ZERO_NON_POSITION_VALUE:
            raise FeatureConventionError(
                f"non-position dimension {key!r} must be {ZERO_NON_POSITION_VALUE} "
                f"(no torque source; send_action hardcodes it), got {value!r}"
            )


# ---------------------------------------------------------------------------
# Acceptance ④ (part) — three-level tracking validity
# ---------------------------------------------------------------------------


class TeleopValidity(IntEnum):
    """VR pose-stream validity: the three-level `OK`/`STALE`/`INVALID` model.

    The integer values are the wire values of the UDP `v`/`vl`/`vr` fields
    (`05` §2.7: 0=OK, 1=STALE, 2=INVALID). `STALE` still publishes — the last pose
    passes through — while `INVALID` stops pose publication and resets the smoother
    (`05` §2.14). This is tracking validity, distinct from the dead-man lease.
    """

    OK = 0
    STALE = 1
    INVALID = 2

    @property
    def is_publishable(self) -> bool:
        """Whether a pose at this validity is still published (OK or STALE)."""
        return self is not TeleopValidity.INVALID


# The `OA-TEL-*` code each non-OK validity surfaces through the shared error envelope.
# `OK` has no code. STALE and INVALID map to the frozen `CTR-ERR@v1` teleop rows
# (`14` §2.10): tracking STALE and tracking INVALID. The string constants are resolved
# to their registry rows, so the severities are the ones `CTR-ERR@v1` froze.
VALIDITY_ERROR_CODES: dict[TeleopValidity, ErrorCode] = {
    TeleopValidity.STALE: REGISTRY.get(codes.OA_TEL_003),
    TeleopValidity.INVALID: REGISTRY.get(codes.OA_TEL_002),
}


def validity_envelope(validity: TeleopValidity) -> ErrorEnvelope | None:
    """Wrap a non-OK tracking validity in the shared CTR-PRIM error envelope.

    Consumes the error-envelope primitive: the code is a registered `OA-TEL-*` and the
    envelope is `CTR-PRIM@v1`'s, not a teleop-local error shape.

    Args:
        validity: A tracking validity level.

    Returns:
        (ErrorEnvelope | None) The wrapped error for STALE/INVALID, or None for OK.
    """
    code = VALIDITY_ERROR_CODES.get(validity)
    if code is None:
        return None
    return error_envelope(code, code.message_en)


# ---------------------------------------------------------------------------
# Acceptance ④ — non-abstract sync_state, operational vs verification-only path
# ---------------------------------------------------------------------------

# The non-abstract method a teleoperator adds so the operational loop can push the
# measured joint angles into the IK configuration before `get_action()` reads it
# (`05` §2.6, `FR-TEL-006`). It takes the robot observation `get_action()` never sees.
SYNC_STATE_METHOD = "sync_state"


class OperationalPath(StrEnum):
    """The two loops that drive the teleoperator, and which one is operational.

    The GUI loop calls `sync_state(obs)` before each `get_action()`, so IK runs
    closed-loop on measured angles. The LeRobot CLI has no injection point, so IK
    integrates open-loop and drifts; the CLI path is therefore verification-only and
    never an operational path (`05` §2.6, `FR-TEL-007`).
    """

    GUI_LOOP = "gui_loop"
    CLI = "cli"

    @property
    def is_operational(self) -> bool:
        """Whether this path may drive the robot in operation (GUI loop only)."""
        return self is OperationalPath.GUI_LOOP


class OpenLoopOperationalError(ValueError):
    """Raised when an operational path would run IK open-loop (no `sync_state`)."""


def require_sync_state_on_operational(path: OperationalPath, calls_sync_state: bool) -> None:
    """Reject an operational loop that does not call `sync_state` before `get_action`.

    Args:
        path: The loop under check.
        calls_sync_state: Whether the loop calls `sync_state(obs)` each tick.

    Raises:
        OpenLoopOperationalError: If an operational path omits `sync_state`, which is
            the `FAIL_BLOCKING` open-loop IK defect (`02b` §5.2 WP-3A-03 negative
            branch). The CLI path is exempt because it is verification-only.
    """
    if path.is_operational and not calls_sync_state:
        raise OpenLoopOperationalError(
            f"operational path {path.value!r} must call {SYNC_STATE_METHOD}(obs) before "
            "get_action(); without it IK runs open-loop (FR-TEL-006/007)"
        )


# ---------------------------------------------------------------------------
# Timestamp domain consumed from CTR-PRIM — dual-timestamp preservation
# ---------------------------------------------------------------------------

# The VR source `t` is the client's clock and the PC receive instant is the server's
# `CLOCK_MONOTONIC`. Both are preserved (`05` §2.7, `WP-3B-07`). The roles are
# `CTR-PRIM@v1`'s: the source is the age input, the receive clock is the server.
SOURCE_TS_ROLE = ClockRole.CLIENT
RECEIVE_TS_ROLE = ClockRole.SERVER


def verify_source_is_age_input(declared: ClockRole) -> None:
    """Enforce that the VR source timestamp is an age input, never an authority.

    Mirrors `CTR-PRIM@v1`'s expiry-owner pin at the teleop boundary: the source `t`
    comes from the headset's clock and cannot be treated as the server authority.

    Args:
        declared: The clock role a consumer assigns to the source timestamp.

    Raises:
        ValueError: If the source is declared anything other than the age-input role.
    """
    if declared != AGE_INPUT_ROLE:
        raise ValueError(
            f"VR source timestamp is pinned to the {AGE_INPUT_ROLE.value} clock (age input); "
            f"a consumer cannot re-own it as {declared.value}"
        )


@dataclass(frozen=True)
class TeleopSample:
    """One received VR pose sample, both timestamps preserved (`05` §2.7).

    Attributes:
        source_ts: The headset-supplied source time (`t`), on the CLIENT clock — an
            age input only, never the expiry/latency authority.
        receive_mono_ns: The PC receive instant, `CLOCK_MONOTONIC` nanoseconds on the
            SERVER clock.
        validity: The three-level tracking validity of this sample.
    """

    source_ts: float
    receive_mono_ns: int
    validity: TeleopValidity

    def __post_init__(self) -> None:
        """Reject a non-integer receive instant — the server clock is monotonic ns."""
        if not isinstance(self.receive_mono_ns, int) or isinstance(self.receive_mono_ns, bool):
            raise ValueError(f"receive_mono_ns must be {CLOCK_SOURCE} int ns")


# ---------------------------------------------------------------------------
# Acceptance ⑤ — reserved KER insertion slot, zero CAN channels
# ---------------------------------------------------------------------------

# The KER teleoperator is USB, not CAN (`05` §2.12, `FR-TEL-062`/`063`): a motorless
# leader read over pyusb. Reserving zero CAN channels is what lets the KER slot be
# inserted barrier-free without changing the CAN DAG (`02b` §5.1 WP-3B-14).
KER_DIST_NAME = "lerobot_teleoperator_openarm_ker"
KER_TELEOP_TYPE = "openarm_ker"
KER_TRANSPORT = "usb"
KER_USB_VID = 0x303A
KER_USB_PID = 0x4002
KER_CAN_CHANNELS = 0
KER_PERFORMS_IK = False


class KerContractError(ValueError):
    """Raised when a KER insertion slot violates the USB / zero-CAN contract."""


@dataclass(frozen=True)
class KerInsertionSlot:
    """The reserved KER teleoperator slot: USB transport, zero CAN channels, no IK.

    Attributes:
        transport: The transport, fixed to `KER_TRANSPORT` (USB).
        usb_vid: The USB vendor id.
        usb_pid: The USB product id.
        can_channels: CAN channels consumed — pinned to zero.
        performs_ik: Whether IK runs — false; the KER returns joint angles directly
            as `.pos` degrees, `.vel`/`.torque` zero (`05` §2.12, `FR-TEL-064`).
    """

    transport: str
    usb_vid: int
    usb_pid: int
    can_channels: int
    performs_ik: bool

    def __post_init__(self) -> None:
        """Reject any slot that is not USB, consumes CAN, or performs IK."""
        if self.transport != KER_TRANSPORT:
            raise KerContractError(
                f"KER transport must be {KER_TRANSPORT!r}, got {self.transport!r}"
            )
        if self.can_channels != KER_CAN_CHANNELS:
            raise KerContractError(
                f"KER slot must consume {KER_CAN_CHANNELS} CAN channels, got {self.can_channels}"
            )
        if self.performs_ik:
            raise KerContractError("KER slot performs no IK; it returns joint angles directly")


def reserved_ker_slot() -> KerInsertionSlot:
    """Return the frozen reserved KER insertion slot.

    Returns:
        (KerInsertionSlot) The USB, zero-CAN, IK-free slot the contract reserves.
    """
    return KerInsertionSlot(
        transport=KER_TRANSPORT,
        usb_vid=KER_USB_VID,
        usb_pid=KER_USB_PID,
        can_channels=KER_CAN_CHANNELS,
        performs_ik=KER_PERFORMS_IK,
    )


def verify_ker_consumes_zero_can(slot: KerInsertionSlot) -> None:
    """Enforce the zero-CAN pin on a KER insertion slot (acceptance ⑤).

    Args:
        slot: The KER slot under check.

    Raises:
        KerContractError: If the slot consumes any CAN channel, which would move it
            onto the CAN DAG and forfeit barrier-free insertion.
    """
    if slot.can_channels != KER_CAN_CHANNELS:
        raise KerContractError(
            f"KER insertion slot must consume {KER_CAN_CHANNELS} CAN channels; "
            f"got {slot.can_channels}, which changes the CAN DAG"
        )
