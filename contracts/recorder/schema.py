"""CTR-REC@v1 — the recorder dataset feature-set contract, consuming CTR-PRIM@v1.

`02b` §5.2 WP-3A-05 freezes the shape of the LeRobot dataset a recording produces:
which feature keys `meta/info.json` may carry, what `action` is, and how the
mixed-unit `observation.state` vector is addressed. It does not restate any shared
primitive — the action payload shape, the camera identifier, the frame-type tag
and the timestamp domain are all *imported* from `contracts.prim` (`CTR-PRIM@v1`),
so a byte here cannot fork one (`02b` §5.0b). The static no-redefinition scan
(`contracts.prim.redefinition`) is what makes that guarantee bite.

The one rule this contract exists to hold (`07` §2.3.3, revision 2026-07-15):

    `action` is the position command that PASSED the safety gate and was actually
    sent to CAN — position only, `SINGLE_ARM_ACTION_DIM`/`BIMANUAL_ACTION_DIM`
    wide, and it stays that width even when `use_velocity_and_torque` is on.
    `send_action()` hardcodes vel/torque to 0.0, so a `.vel`/`.torque` value is
    neither a robot command nor a leader-measured torque; recording it as an
    `action` dimension trains the policy on a command that never existed. A
    torque dimension entering `action` is the `FAIL_BLOCKING` defect.

Velocity and torque survive only in `observation.state`, interleaved per motor and
addressed by name suffix (`07` §2.3.2) — never by a hardcoded index, because the
width collapses from 24/48 to 8/16 the moment `use_velocity_and_torque` is off.

Freeze mechanics (`02b` §5.2, `06` §4.3): this module is the DRAFT source of truth.
`WP-3A-06` freezes `CTR-REC@v1` by materialising the canonical body
`contracts/recorder/schema.json` from `frozen_json_text()` and appending one FREEZE
event to the chained ledger — the consumers are frozen sequentially there to avoid
a parallel-append race, so nothing in this wave touches the ledger. Until then the
`CONTRACT_FROZEN` glob (`contracts/recorder/schema.json`) has no on-disk body, which
is exactly why CI-09 stays green while the contract is DRAFT (`06` §4.3: the hash
lock applies only after freeze).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from contracts.prim import (
    ACTION_IS_POSITION_ONLY,
    ACTION_POSITION_UNIT,
    ARM_PREFIXES,
    ARM_SIDES,
    BIMANUAL_ACTION_DIM,
    DEPTH_KEY_SUFFIX,
    FRAME_TYPE_CHANNELS,
    FRAME_TYPE_DTYPE,
    IMAGE_KEY_PREFIX,
    REQUIRED_FRAME_TYPE,
    SINGLE_ARM_ACTION_DIM,
    CameraSlotKey,
    FrameType,
    TimestampDomain,
)
from contracts.prim import CONTRACT_ID as PRIM_CONTRACT_ID
from ops.hubguard.push_policy import (
    ENFORCED_PUSH_TO_HUB_DEFAULT,
    RecordConfigView,
    UploadDecision,
    resolve_push_to_hub,
)

# The contract id this module is the DRAFT body of. `WP-3A-06` freezes this exact
# string; the freeze check, the staleness axis and the no-redefinition scan all
# key on it, so it is named once (`02b` §5.2 WP-3A-05).
CONTRACT_ID = "CTR-REC@v1"

# The frozen generation. A shape change is `CTR-REC@v2`, never an in-place edit of
# this literal (`06` §4.3).
SCHEMA_VERSION = 1

# The single upstream contract this schema consumes by reference. `CTR-PRIM@v1`
# holds the action shape, camera identifier, frame-type and timestamp domain; a
# `CTR-PRIM` major bump supersedes this contract (`CI-03d`, `CR-2`).
CONSUMED_CONTRACTS = (PRIM_CONTRACT_ID,)


class RecorderContractError(ValueError):
    """Raised when a dataset shape violates `CTR-REC@v1`.

    The blocking cases (`02b` §5.2 WP-3A-05 negative branch): an out-of-contract
    key in `info.json`, an `action` feature carrying a `.vel`/`.torque` dimension,
    or a `use_velocity_and_torque` switch set independently for leader and follower.
    """


# ---------------------------------------------------------------------------
# Motor identity — the per-arm motor order the dataset feature names are built on
# ---------------------------------------------------------------------------

# The eight follower motors in `motor_config` dict order (`07` §2.3:
# `config_openarm_follower.py`). The order is load-bearing: it fixes the position
# of every `observation.state` channel, so it is declared once and never sorted.
MOTOR_NAMES = (
    "joint_1",
    "joint_2",
    "joint_3",
    "joint_4",
    "joint_5",
    "joint_6",
    "joint_7",
    "gripper",
)
MOTORS_PER_ARM = len(MOTOR_NAMES)

# The per-motor feature suffixes. `.pos` is always present; `.vel`/`.torque` appear
# only under `use_velocity_and_torque` (`07` §2.3). `.pos`'s unit is the action
# position unit imported from `CTR-PRIM@v1`, not restated here.
POSITION_SUFFIX = ".pos"
VELOCITY_SUFFIX = ".vel"
TORQUE_SUFFIX = ".torque"
PER_MOTOR_SUFFIXES_FULL = (POSITION_SUFFIX, VELOCITY_SUFFIX, TORQUE_SUFFIX)
PER_MOTOR_SUFFIXES_MIN = (POSITION_SUFFIX,)

# The unit each suffix carries inside the single `observation.state` vector
# (`07` §2.4): position and velocity pass through `np.degrees()`, torque leaves in
# native `Nm`. This mixed-unit fact is what the contract records in meta so a
# consumer cannot read a torque channel as if it were degrees. `.pos` reuses the
# `CTR-PRIM@v1` action unit; `.vel`/`.torque` are the observation-only labels.
POSITION_UNIT = ACTION_POSITION_UNIT
VELOCITY_UNIT = "deg/s"
TORQUE_UNIT = "Nm"
SUFFIX_UNITS = {
    POSITION_SUFFIX: POSITION_UNIT,
    VELOCITY_SUFFIX: VELOCITY_UNIT,
    TORQUE_SUFFIX: TORQUE_UNIT,
}


# ---------------------------------------------------------------------------
# The dataset feature-key namespace — exactly this set, no other key
# ---------------------------------------------------------------------------

# The two non-image feature keys (`utils/constants.py`: `ACTION`, `OBS_STR`).
ACTION_KEY = "action"
OBSERVATION_STATE_KEY = "observation.state"

# The five default meta features LeRobot merges into every dataset
# (`dataset_metadata.py`: `DEFAULT_FEATURES`, `07` §2.2). `timestamp` is the
# synthetic playback grid (`frame_index / fps`), NOT a capture instant — it is the
# `CTR-PRIM@v1` `SYNTHETIC_GRID` domain, and the contract records that so a consumer
# cannot mistake it for a real capture time.
META_FEATURES = ("timestamp", "frame_index", "episode_index", "index", "task_index")
TIMESTAMP_META_KEY = "timestamp"
TIMESTAMP_DOMAIN = TimestampDomain.SYNTHETIC_GRID


# ---------------------------------------------------------------------------
# use_velocity_and_torque — one switch for follower AND leader
# ---------------------------------------------------------------------------

# The upstream default (`07` §2.5: `use_velocity_and_torque: bool = False`). One
# switch drives both the follower feature width and the leader, so a per-side UI is
# a `FAIL_BLOCKING` defect (`02b` §5.2 WP-3A-05 ⑥): a follower-only `True` yields an
# `observation.state`/`action` mismatch that stops recording (`OA-DAT-004`).
DEFAULT_USE_VELOCITY_AND_TORQUE = False


def resolve_velocity_torque_switch(follower: bool, leader: bool) -> bool:
    """Collapse a follower and a leader flag into the one shared switch, or refuse.

    `02b` §5.2 WP-3A-05 ⑥ requires `use_velocity_and_torque` to be a single
    follower+leader switch; two independently settable flags are the individual-UI
    defect. This is the contract-level guard that refuses the split.

    Args:
        follower: The follower's `use_velocity_and_torque` value.
        leader: The leader's `use_velocity_and_torque` value.

    Returns:
        (bool) The single shared value when the two agree.

    Raises:
        RecorderContractError: When the two disagree — the individual-switch defect.
    """
    if follower != leader:
        raise RecorderContractError(
            "use_velocity_and_torque must be a single follower+leader switch; "
            f"got follower={follower} leader={leader} (individual switch is FAIL_BLOCKING)"
        )
    return follower


@dataclass(frozen=True)
class RecorderConfig:
    """The recording knobs that shape the dataset feature set.

    Attributes:
        bimanual: Two arms when True, one when False; fixes the action width to
            `BIMANUAL_ACTION_DIM`/`SINGLE_ARM_ACTION_DIM`.
        use_velocity_and_torque: The single follower+leader switch. When True,
            `observation.state` gains `.vel`/`.torque` channels; `action` never does.
        camera_slots: The camera identifiers whose RGB streams are recorded, as
            `CTR-PRIM@v1` slot keys — the sole source of the `observation.images.*`
            keys, so no layer restates the camera identifier.
        depth_slots: The subset of `camera_slots` that also record a depth stream.
        push_to_hub: The user's `push_to_hub` request; `None` means unspecified and
            resolves to `False` through the `WP-OPS-04` hub guard.
    """

    bimanual: bool
    use_velocity_and_torque: bool = DEFAULT_USE_VELOCITY_AND_TORQUE
    camera_slots: tuple[CameraSlotKey, ...] = ()
    depth_slots: frozenset[CameraSlotKey] = field(default_factory=frozenset)
    push_to_hub: bool | None = None

    def __post_init__(self) -> None:
        """Reject a depth slot that is not also an RGB slot — depth has no RGB-less key."""
        stray = self.depth_slots - set(self.camera_slots)
        if stray:
            raise RecorderContractError(
                f"depth slots {sorted(s.value for s in stray)} are not registered RGB camera slots"
            )


# ---------------------------------------------------------------------------
# Feature-name derivation — position-only action, interleaved observation.state
# ---------------------------------------------------------------------------


def motor_keys(bimanual: bool) -> tuple[str, ...]:
    """Return the ordered motor keys, arm-prefixed and left-first when bimanual.

    The bimanual prefix reuses the `CTR-PRIM@v1` arm-prefix grammar (`ARM_PREFIXES`,
    left before right — `07` §2.3.1), so a motor key and a per-arm camera key carry
    the same `left_`/`right_` convention.

    Args:
        bimanual: Whether both arms are present.

    Returns:
        (tuple[str, ...]) Motor keys in dataset order.
    """
    if not bimanual:
        return MOTOR_NAMES
    keys: list[str] = []
    for side in ARM_SIDES:
        keys.extend(f"{ARM_PREFIXES[side]}{motor}" for motor in MOTOR_NAMES)
    return tuple(keys)


def action_dim(bimanual: bool) -> int:
    """Return the frozen `action` width, imported from `CTR-PRIM@v1`.

    Args:
        bimanual: Whether both arms are present.

    Returns:
        (int) `BIMANUAL_ACTION_DIM` or `SINGLE_ARM_ACTION_DIM` — position only, and
            independent of `use_velocity_and_torque`.
    """
    return BIMANUAL_ACTION_DIM if bimanual else SINGLE_ARM_ACTION_DIM


def action_names(bimanual: bool) -> tuple[str, ...]:
    """Return the `action` feature names — position only, one `.pos` per motor.

    Args:
        bimanual: Whether both arms are present.

    Returns:
        (tuple[str, ...]) `<motor>.pos` names, length `action_dim(bimanual)`; never
            a `.vel`/`.torque` name (`07` §2.3.3, the FAIL_BLOCKING rule).
    """
    return tuple(f"{key}{POSITION_SUFFIX}" for key in motor_keys(bimanual))


def observation_state_names(bimanual: bool, use_velocity_and_torque: bool) -> tuple[str, ...]:
    """Return the `observation.state` names, interleaved per motor.

    Each motor contributes `(.pos, .vel, .torque)` when `use_velocity_and_torque`
    else `(.pos,)`; the block is arm-major (left then right) when bimanual, so the
    width is 8/24 single or 16/48 bimanual (`07` §2.3.1/§2.3.2).

    Args:
        bimanual: Whether both arms are present.
        use_velocity_and_torque: Whether velocity and torque channels are recorded.

    Returns:
        (tuple[str, ...]) Interleaved `observation.state` channel names.
    """
    suffixes = PER_MOTOR_SUFFIXES_FULL if use_velocity_and_torque else PER_MOTOR_SUFFIXES_MIN
    return tuple(f"{key}{suffix}" for key in motor_keys(bimanual) for suffix in suffixes)


def index_of(names: Sequence[str], motor: str, suffix: str) -> int:
    """Look up a channel's index in an `observation.state` name list, by string.

    This is the addressing the contract mandates (`07` §2.3.2, `FR-REC-006`): a
    consumer that wants a motor's torque asks for it by name and never hardcodes an
    index, because the index moves when `use_velocity_and_torque` toggles.

    Args:
        names: The `observation.state` `names` list from `meta/info.json`.
        motor: A motor key (e.g. `left_gripper`).
        suffix: One of `.pos`/`.vel`/`.torque`.

    Returns:
        (int) The channel's position in `names`.

    Raises:
        RecorderContractError: When the channel is absent — e.g. asking for a
            `.torque` channel a `use_velocity_and_torque=False` dataset never wrote.
    """
    key = f"{motor}{suffix}"
    try:
        return list(names).index(key)
    except ValueError as absent:
        raise RecorderContractError(
            f"channel {key!r} is not in observation.state names; "
            "query by suffix and do not assume a fixed index"
        ) from absent


def channels_with_suffix(names: Sequence[str], suffix: str) -> tuple[int, ...]:
    """Return the indices of every channel carrying a given suffix, by string match.

    Args:
        names: The `observation.state` `names` list.
        suffix: One of `.pos`/`.vel`/`.torque`.

    Returns:
        (tuple[int, ...]) Positions of matching channels, in list order.
    """
    return tuple(index for index, name in enumerate(names) if name.endswith(suffix))


# ---------------------------------------------------------------------------
# The dataset feature set — exactly this key set, no other
# ---------------------------------------------------------------------------


def image_feature_keys(config: RecorderConfig) -> tuple[str, ...]:
    """Return the `observation.images.*` keys for a config, via `CTR-PRIM@v1` joins.

    Each RGB slot renders through `CameraSlotKey.image_key()` and each depth slot
    additionally through `depth_key()`, so the recorder never spells the image-key
    grammar itself (`02b` §5.0b row 1).

    Args:
        config: The recording configuration.

    Returns:
        (tuple[str, ...]) Image feature keys in slot order, RGB before depth.
    """
    keys: list[str] = []
    for slot in config.camera_slots:
        keys.append(slot.image_key())
        if slot in config.depth_slots:
            keys.append(slot.depth_key())
    return tuple(keys)


def allowed_info_keys(config: RecorderConfig) -> frozenset[str]:
    """Return every feature key `meta/info.json` is permitted to carry.

    This is the closed set acceptance ② checks against: `action`,
    `observation.state`, the configured `observation.images.*` keys, and the five
    meta features. Anything else is out of contract.

    Args:
        config: The recording configuration.

    Returns:
        (frozenset[str]) The permitted `info.json` feature keys.
    """
    return frozenset(
        {ACTION_KEY, OBSERVATION_STATE_KEY, *image_feature_keys(config), *META_FEATURES}
    )


def _image_feature_spec(frame_type: FrameType) -> dict[str, object]:
    """Build the `info.json` feature body for one image stream.

    Args:
        frame_type: RGB or depth; fixes channel count and dtype from `CTR-PRIM@v1`.

    Returns:
        (dict) The `{dtype, shape, names, is_depth_map}` feature body.
    """
    channels = FRAME_TYPE_CHANNELS[frame_type]
    return {
        "dtype": FRAME_TYPE_DTYPE[frame_type],
        "shape": ["height", "width", channels],
        "names": ["height", "width", "channels"],
        "is_depth_map": frame_type == FrameType.DEPTH,
    }


def feature_set(config: RecorderConfig) -> dict[str, dict[str, object]]:
    """Build the full `meta/info.json` feature set for a configuration.

    The `action` body is position only at `action_dim(config.bimanual)`; the
    `observation.state` body carries the interleaved names; images come from the
    `CTR-PRIM@v1` slot joins; the five meta features are appended. No other key is
    produced (`02b` §5.2 WP-3A-05 ②).

    Args:
        config: The recording configuration.

    Returns:
        (dict) Feature key to its `info.json` body.
    """
    state_names = observation_state_names(config.bimanual, config.use_velocity_and_torque)
    features: dict[str, dict[str, object]] = {
        ACTION_KEY: {
            "dtype": "float32",
            "shape": [action_dim(config.bimanual)],
            "names": list(action_names(config.bimanual)),
        },
        OBSERVATION_STATE_KEY: {
            "dtype": "float32",
            "shape": [len(state_names)],
            "names": list(state_names),
        },
    }
    for slot in config.camera_slots:
        features[slot.image_key()] = _image_feature_spec(REQUIRED_FRAME_TYPE)
        if slot in config.depth_slots:
            features[slot.depth_key()] = _image_feature_spec(FrameType.DEPTH)
    for meta_key in META_FEATURES:
        features[meta_key] = {"dtype": "int64" if meta_key != TIMESTAMP_META_KEY else "float32"}
    return features


# ---------------------------------------------------------------------------
# Validation — the acceptance checks a produced info.json must pass
# ---------------------------------------------------------------------------


def _validate_action(body: Mapping[str, Any], bimanual: bool) -> None:
    """Enforce that `action` is position only at the frozen width.

    Args:
        body: The `action` feature body from `info.json`.
        bimanual: Whether both arms are present.

    Raises:
        RecorderContractError: When the width is wrong, or any name is a `.vel`/
            `.torque` channel — the leader-torque-poisons-the-target defect.
    """
    names = list(body.get("names", []))
    poisoned = [name for name in names if name.endswith((VELOCITY_SUFFIX, TORQUE_SUFFIX))]
    if poisoned:
        raise RecorderContractError(
            f"action carries non-position dimensions {poisoned}; action is the position command "
            "sent to CAN, never a .vel/.torque value (FAIL_BLOCKING)"
        )
    if tuple(names) != action_names(bimanual):
        raise RecorderContractError(
            f"action names {names} are not the position-only set for bimanual={bimanual}"
        )
    shape = list(body.get("shape", []))
    if shape != [action_dim(bimanual)]:
        raise RecorderContractError(
            f"action shape {shape} is not [{action_dim(bimanual)}]; action width is position only "
            "and independent of use_velocity_and_torque"
        )


def validate_info_features(features: Mapping[str, Any], config: RecorderConfig) -> None:
    """Validate a produced `meta/info.json` feature map against `CTR-REC@v1`.

    Checks the closed key set (②), the position-only `action` (① and the torque
    FAIL_BLOCKING rule), and that `observation.state` matches the interleaved names.

    Args:
        features: The `features` map from `meta/info.json`.
        config: The recording configuration the dataset was produced under.

    Raises:
        RecorderContractError: On any out-of-contract key, a poisoned `action`, or
            an `observation.state` mismatch.
    """
    present = set(features)
    extra = present - allowed_info_keys(config)
    if extra:
        raise RecorderContractError(
            f"info.json carries out-of-contract keys {sorted(extra)}; the feature set is closed"
        )
    missing = {ACTION_KEY, OBSERVATION_STATE_KEY, *META_FEATURES} - present
    if missing:
        raise RecorderContractError(f"info.json is missing required features {sorted(missing)}")

    action_body = features[ACTION_KEY]
    if not isinstance(action_body, Mapping):
        raise RecorderContractError("action feature body must be a mapping")
    _validate_action(action_body, config.bimanual)

    state_body = features[OBSERVATION_STATE_KEY]
    if not isinstance(state_body, Mapping):
        raise RecorderContractError("observation.state feature body must be a mapping")
    expected = list(observation_state_names(config.bimanual, config.use_velocity_and_torque))
    if list(state_body.get("names", [])) != expected:
        raise RecorderContractError("observation.state names do not match the interleaved contract")


# ---------------------------------------------------------------------------
# push_to_hub — default false, through the WP-OPS-04 hub guard (reused, not restated)
# ---------------------------------------------------------------------------


def push_to_hub_decision(config: RecorderConfig) -> UploadDecision:
    """Resolve `push_to_hub` for a config through the `WP-OPS-04` hub guard.

    Acceptance ⑤: an unspecified `push_to_hub` resolves to `False`. The policy is
    not restated here — it is `ops.hubguard.push_policy`, so there is one place the
    upstream `True` default is overturned.

    Args:
        config: The recording configuration.

    Returns:
        (UploadDecision) The resolved value; `False` unless the user both requested
            and confirmed an upload.
    """
    return resolve_push_to_hub(RecordConfigView(push_to_hub=config.push_to_hub), confirmation=None)


# ---------------------------------------------------------------------------
# The frozen canonical body — materialised and locked by WP-3A-06
# ---------------------------------------------------------------------------


def unit_convention() -> dict[str, str]:
    """Return the per-suffix unit map recorded in meta (`07` §2.4).

    Returns:
        (dict[str, str]) `.pos`->deg, `.vel`->deg/s, `.torque`->Nm, the mixed units
            a single `observation.state` vector carries.
    """
    return dict(SUFFIX_UNITS)


def frozen_document() -> dict[str, Any]:
    """Return the config-agnostic canonical description of `CTR-REC@v1`.

    This is the body `WP-3A-06` serialises to `contracts/recorder/schema.json` and
    freezes by content hash. Every shape value is imported from `CTR-PRIM@v1`, so
    the frozen artifact itself consumes the primitives rather than restating them.

    Returns:
        (dict) The canonical, deterministically serialisable contract body.
    """
    return {
        "contract": CONTRACT_ID,
        "schema_version": SCHEMA_VERSION,
        "consumes": list(CONSUMED_CONTRACTS),
        "action": {
            "position_only": ACTION_IS_POSITION_ONLY,
            "unit": POSITION_UNIT,
            "single_arm_dim": SINGLE_ARM_ACTION_DIM,
            "bimanual_dim": BIMANUAL_ACTION_DIM,
            "forbidden_suffixes": [VELOCITY_SUFFIX, TORQUE_SUFFIX],
            "definition": "position command that passed the safety gate and was sent to CAN",
        },
        "observation_state": {
            "per_motor_suffixes_full": list(PER_MOTOR_SUFFIXES_FULL),
            "per_motor_suffixes_min": list(PER_MOTOR_SUFFIXES_MIN),
            "single_arm_dims": {"position_only": MOTORS_PER_ARM, "full": MOTORS_PER_ARM * 3},
            "bimanual_dims": {"position_only": MOTORS_PER_ARM * 2, "full": MOTORS_PER_ARM * 2 * 3},
            "interleave": "per_motor",
            "address_by": "name_suffix",
        },
        "motors": {
            "per_arm": list(MOTOR_NAMES),
            "arm_prefixes": {side: ARM_PREFIXES[side] for side in ARM_SIDES},
            "left_first": True,
        },
        "images": {
            "rgb_key": f"{IMAGE_KEY_PREFIX}<slot>",
            "depth_key": f"{IMAGE_KEY_PREFIX}<slot>{DEPTH_KEY_SUFFIX}",
            "required_frame_type": REQUIRED_FRAME_TYPE.value,
        },
        "meta_features": list(META_FEATURES),
        "timestamp_domain": TIMESTAMP_DOMAIN.value,
        "unit_convention": unit_convention(),
        "push_to_hub": {
            "default": ENFORCED_PUSH_TO_HUB_DEFAULT,
            "enforced_by": "WP-OPS-04 hub guard",
        },
        "use_velocity_and_torque": {
            "default": DEFAULT_USE_VELOCITY_AND_TORQUE,
            "scope": "single follower+leader switch",
        },
        "info_key_rule": (
            "exactly {action, observation.state, observation.images.<slot>[, <slot>_depth], "
            "timestamp, frame_index, episode_index, index, task_index}; no other key"
        ),
    }


def frozen_json_text() -> str:
    """Return the deterministic JSON serialisation of the frozen body.

    Sorted keys and a trailing newline make the content hash reproducible, so
    `WP-3A-06`'s freeze and CI-09's later re-hash lock the same bytes.

    Returns:
        (str) The canonical JSON text of `frozen_document()`.
    """
    return json.dumps(frozen_document(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_frozen_json(path: str) -> None:
    """Write the frozen body to `path` — the `WP-3A-06` materialisation step.

    Args:
        path: Destination for `contracts/recorder/schema.json`.
    """
    Path(path).write_text(frozen_json_text(), encoding="utf-8")
