"""Channel and camera-stream structure, derived from `meta/info.json` alone.

`FR-DAT-011` acceptance ①: stream count and type are read from the dataset's
`info.json`, never assumed from a fixed slot list. This module is that derivation
— it enumerates the `observation.images.*` features, classifies each as RGB or
depth, and parses the `observation.state`/`action` channel names into per-motor,
unit-labelled channels. The camera identifier and image-key grammar are
`CTR-PRIM@v1` primitives, imported from `contracts.prim`; the unit convention is
mirrored from `CTR-REC@v1` through the `names` strings (see `constants`).

`FR-DAT-012`/`FR-DAT-016` live here too: axis units come from the channel-name
suffix, and following error is defined on position channels only — a `.vel`/
`.torque` name appearing in `action` is the FAIL_BLOCKING poison and is refused,
never plotted as a "leader-measured torque".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from backend.dataset.viewer.constants import (
    ACTION_KEY,
    FEATURE_IS_DEPTH_KEY,
    FEATURE_NAMES_KEY,
    FEATURE_SHAPE_KEY,
    OBSERVATION_STATE_KEY,
    POSITION_SUFFIX,
    SUFFIX_UNITS,
    TORQUE_SUFFIX,
    UNKNOWN_UNIT,
    VELOCITY_SUFFIX,
)
from contracts.prim import (
    DEPTH_KEY_SUFFIX,
    IMAGE_KEY_PREFIX,
    CameraSlotKey,
    FrameType,
    slot_from_image_key,
)


class ViewerChannelError(ValueError):
    """Raised when `info.json` channel structure is unreadable or self-contradictory.

    Distinct from a layout/IO error: this is a malformed feature set (a missing
    `names` list, or an `action` feature carrying a torque channel), not a missing
    file. An `action.torque` name is the `07` §2.3.3 FAIL_BLOCKING case surfaced
    at read time rather than silently plotted.
    """


def unit_for_channel(name: str) -> str:
    """Return the display unit for a channel, from its name suffix.

    Args:
        name: A channel name such as `left_joint_1.pos` or `right_gripper.torque`.

    Returns:
        (str) `deg`/`deg/s`/`Nm` per the `CTR-REC@v1` convention, or `UNKNOWN_UNIT`
            when the name carries no recognised suffix (shown, never blanked).
    """
    for suffix, unit in SUFFIX_UNITS.items():
        if name.endswith(suffix):
            return unit
    return UNKNOWN_UNIT


def axis_label(name: str) -> str:
    """Return a channel's axis label with its unit, e.g. `left_joint_1.pos [deg]`.

    Args:
        name: A channel name.

    Returns:
        (str) The name annotated with its bracketed unit (`FR-DAT-016`).
    """
    return f"{name} [{unit_for_channel(name)}]"


@dataclass(frozen=True)
class CameraStream:
    """One configured camera stream, as `info.json` declares it.

    Attributes:
        image_key: The full `observation.images.<slot>[_depth]` feature key.
        slot: The base camera slot the stream belongs to (RGB and depth of one
            camera share a slot), a `CTR-PRIM@v1` `CameraSlotKey`.
        frame_type: RGB or DEPTH, the `CTR-PRIM@v1` frame-type primitive.
        shape: The `[height, width, channels]` shape from the feature body.
    """

    image_key: str
    slot: CameraSlotKey
    frame_type: FrameType
    shape: tuple[int | str, ...]

    @property
    def is_depth(self) -> bool:
        """Whether this stream carries depth rather than RGB."""
        return self.frame_type == FrameType.DEPTH


@dataclass(frozen=True)
class FollowingErrorPair:
    """A position channel's follower/leader index pair for following error.

    Following error is `observation.state[<motor>.pos] - action[<motor>.pos]` and
    is defined on position channels only (`FR-DAT-012`); torque and velocity have
    no `action` counterpart and never enter this pairing.

    Attributes:
        motor: The motor key the pair belongs to (e.g. `left_gripper`).
        state_index: Column of `<motor>.pos` in `observation.state`.
        action_index: Column of `<motor>.pos` in `action`.
    """

    motor: str
    state_index: int
    action_index: int


def _feature_body(features: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    """Return a feature body, or raise when it is absent or not a mapping."""
    body = features.get(key)
    if not isinstance(body, Mapping):
        raise ViewerChannelError(f"info.json feature {key!r} is missing or not an object")
    return body


def _names(features: Mapping[str, Any], key: str) -> tuple[str, ...]:
    """Return a feature's channel `names`, or raise when absent."""
    body = _feature_body(features, key)
    names = body.get(FEATURE_NAMES_KEY)
    if not isinstance(names, Sequence) or isinstance(names, str) or not names:
        raise ViewerChannelError(
            f"info.json feature {key!r} has no usable {FEATURE_NAMES_KEY!r} list"
        )
    return tuple(str(name) for name in names)


def state_channel_names(features: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the `observation.state` channel names in dataset order."""
    return _names(features, OBSERVATION_STATE_KEY)


def action_channel_names(features: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the `action` channel names, verifying they are position only.

    Raises:
        ViewerChannelError: If any `action` name carries a `.vel`/`.torque`
            suffix — the `07` §2.3.3 poison the viewer must never display as a
            leader-measured value.
    """
    names = _names(features, ACTION_KEY)
    poisoned = [name for name in names if name.endswith((VELOCITY_SUFFIX, TORQUE_SUFFIX))]
    if poisoned:
        raise ViewerChannelError(
            f"action carries non-position channels {poisoned}; action is position only "
            "and a .vel/.torque value is neither a robot command nor a leader-measured torque"
        )
    return names


def following_error_pairs(features: Mapping[str, Any]) -> tuple[FollowingErrorPair, ...]:
    """Pair each position channel across `observation.state` and `action`.

    Only `.pos` channels are paired; a motor whose `.pos` appears in one feature
    but not the other is skipped rather than guessed. The result drives per-joint
    following error (`FR-DAT-012`).

    Args:
        features: The `info.json` feature map.

    Returns:
        (tuple[FollowingErrorPair, ...]) One pair per position channel shared by
            both features, in `observation.state` order.
    """
    state_names = state_channel_names(features)
    action_names = action_channel_names(features)
    action_index = {name: index for index, name in enumerate(action_names)}

    pairs: list[FollowingErrorPair] = []
    for state_idx, name in enumerate(state_names):
        if not name.endswith(POSITION_SUFFIX):
            continue
        act_idx = action_index.get(name)
        if act_idx is None:
            continue
        motor = name[: -len(POSITION_SUFFIX)]
        pairs.append(FollowingErrorPair(motor=motor, state_index=state_idx, action_index=act_idx))
    return tuple(pairs)


def _classify_frame_type(image_key: str, body: Mapping[str, Any]) -> FrameType:
    """Classify a stream as depth or RGB from `is_depth_map`, then the key suffix.

    The `is_depth_map` flag is authoritative; the `_depth` key suffix is the
    fallback for a dataset that omitted the flag. Both agree by construction under
    `CTR-REC@v1`, so this only diverges on a malformed dataset, where the flag wins.
    """
    flagged = bool(body.get(FEATURE_IS_DEPTH_KEY, False))
    if flagged or image_key.endswith(DEPTH_KEY_SUFFIX):
        return FrameType.DEPTH
    return FrameType.RGB


def _base_slot(image_key: str, frame_type: FrameType) -> CameraSlotKey:
    """Recover the base camera slot from an image key, stripping any depth suffix.

    RGB and depth of one camera share a slot; the depth key carries the `_depth`
    suffix on top of the slot, so it is stripped before the `CTR-PRIM@v1` grammar
    recovers the slot.
    """
    if frame_type == FrameType.DEPTH and image_key.endswith(DEPTH_KEY_SUFFIX):
        return CameraSlotKey(image_key[len(IMAGE_KEY_PREFIX) : -len(DEPTH_KEY_SUFFIX)])
    return slot_from_image_key(image_key)


def camera_streams(features: Mapping[str, Any]) -> tuple[CameraStream, ...]:
    """Enumerate the configured camera streams from `info.json`.

    A stream is any feature whose key carries the `CTR-PRIM@v1` image prefix. The
    count and RGB/depth split come from the feature set, never a fixed slot table
    (`FR-DAT-011` acceptance ①). Streams are returned in feature-declaration order.

    Args:
        features: The `info.json` feature map.

    Returns:
        (tuple[CameraStream, ...]) The configured streams, RGB and depth alike.
    """
    streams: list[CameraStream] = []
    for image_key, body in features.items():
        if not image_key.startswith(IMAGE_KEY_PREFIX):
            continue
        if not isinstance(body, Mapping):
            raise ViewerChannelError(f"image feature {image_key!r} body is not an object")
        frame_type = _classify_frame_type(image_key, body)
        raw_shape = body.get(FEATURE_SHAPE_KEY, [])
        # info.json shapes carry symbolic dims ("height"/"width") beside integer
        # channel counts; both are preserved as declared, not coerced away.
        shape: tuple[int | str, ...] = (
            tuple(dim if isinstance(dim, str) else int(dim) for dim in raw_shape)
            if isinstance(raw_shape, Sequence) and not isinstance(raw_shape, str)
            else ()
        )
        streams.append(
            CameraStream(
                image_key=image_key,
                slot=_base_slot(image_key, frame_type),
                frame_type=frame_type,
                shape=shape,
            )
        )
    return tuple(streams)
