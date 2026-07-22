"""Provenance-gated loading of a v1-derived dynamics asset and its conversion to the v2 frame.

Two guards stand between a stored asset and the v2 runtime:

* Provenance (FR-SAF-067): a safety parameter without a complete
  `{source_repo, commit_sha, path, robot_version, identified_on}` stamp is unloadable, and
  under strict mode a stamp whose `robot_version != "2.0"` is refused rather than warned.
* Convertibility (FR-SAF-033): three items have no v2 representation — a link7 inertia, the
  rotated base_link inertia frame, and any gripper/finger model — so an asset carrying one is
  refused with the reason, rather than converted into a silent error.

`convert_v1_to_v2` is the explicit promotion path: it applies the joint-frame converter to the
v1 seed, refuses any unconvertible item, and re-stamps the result with fresh v2 provenance so a
converted asset is a first-class v2 asset that passes the strict gate, not a v1 asset in disguise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.dynamics.constants import (
    ANGLE_VECTOR_FIELDS,
    GRIPPER_MODEL_KEYS,
    GRIPPER_MODEL_REASON,
    ROBOT_VERSION_V2,
    TORQUE_VECTOR_FIELDS,
    UNCONVERTIBLE_INERTIAL_LINKS,
)
from backend.dynamics.converter import JointFrameConverter
from backend.dynamics.errors import DynamicsConversionError
from backend.dynamics.provenance import Provenance

PROVENANCE_KEY = "provenance"


@dataclass(frozen=True)
class UnconvertibleItem:
    """One reason a v1 asset cannot be carried to v2.

    Attributes:
        item: The offending item name ("link7", "base_link", "gripper_model", ...).
        reason: Why it has no v2 representation.
    """

    item: str
    reason: str


@dataclass
class LoadedDynamicsAsset:
    """A dynamics asset that passed the provenance gate, plus any non-fatal warnings.

    Attributes:
        provenance: The validated origin stamp.
        payload: The asset body with `provenance` removed (opaque to this WP).
        warnings: Non-fatal load warnings. Under strict mode a wrong `robot_version` is a
            refusal, so a populated list here occurs only in non-strict mode.
    """

    provenance: Provenance
    payload: dict[str, Any]
    warnings: tuple[str, ...] = ()


def unconvertible_items(asset: dict[str, Any]) -> tuple[UnconvertibleItem, ...]:
    """List every part of a v1 asset that has no v2 representation (FR-SAF-033).

    The scan covers the two carriers of the offending items: an `inertials` mapping whose keys
    name links, and a top-level gripper/finger model key. Every unconvertible item is returned
    (not just the first) so a refusal can name them all at once.

    Args:
        asset: A parsed v1 dynamics asset.

    Returns:
        (tuple[UnconvertibleItem, ...]) The unconvertible items found, in a stable order.
    """
    found: list[UnconvertibleItem] = []
    inertials = asset.get("inertials", {})
    if isinstance(inertials, dict):
        for link, reason in UNCONVERTIBLE_INERTIAL_LINKS.items():
            if link in inertials:
                found.append(UnconvertibleItem(link, reason))
    for key in GRIPPER_MODEL_KEYS:
        if asset.get(key) is not None:
            found.append(UnconvertibleItem(key, GRIPPER_MODEL_REASON))
    return tuple(found)


def load_safety_params(raw: dict[str, Any], strict: bool = True) -> LoadedDynamicsAsset:
    """Load a safety-parameter asset behind the provenance and version gates (FR-SAF-067).

    Args:
        raw: A parsed asset mapping; must carry a `provenance` mapping.
        strict: When True (the v2 runtime default), a `robot_version != "2.0"` stamp is
            refused. When False, it loads with a warning instead.

    Returns:
        (LoadedDynamicsAsset) The asset with its validated provenance and any warnings.

    Raises:
        DynamicsConversionError: On a non-mapping asset, missing or incomplete provenance, or
            a non-"2.0" robot_version under strict mode.
    """
    if not isinstance(raw, dict):
        raise DynamicsConversionError(f"asset must be a mapping, got {type(raw).__name__}")
    if PROVENANCE_KEY not in raw:
        raise DynamicsConversionError(
            "asset carries no provenance; a safety parameter without provenance is unloadable "
            "(FR-SAF-067)"
        )
    provenance = Provenance.from_mapping(raw[PROVENANCE_KEY], "asset")
    payload = {key: value for key, value in raw.items() if key != PROVENANCE_KEY}

    warnings: list[str] = []
    if not provenance.is_v2():
        message = (
            f"asset robot_version is {provenance.robot_version!r}, not {ROBOT_VERSION_V2!r}: a "
            "v1-generation parameter in the v2 runtime is model contamination (FR-SAF-067)"
        )
        if strict:
            raise DynamicsConversionError(f"strict mode blocks load: {message}")
        warnings.append(message)

    return LoadedDynamicsAsset(provenance=provenance, payload=payload, warnings=tuple(warnings))


def convert_v1_to_v2(
    v1_asset: dict[str, Any],
    converter: JointFrameConverter,
    v2_provenance: Provenance,
) -> LoadedDynamicsAsset:
    """Convert a v1 seed asset to a v2 asset, refusing any unconvertible item (FR-SAF-033).

    The conversion is explicit and re-stamps provenance: the caller supplies the frame
    converter and the new v2 provenance (robot_version "2.0", the conversion's own
    identified_on), so the result is a first-class v2 asset that passes the strict gate rather
    than a v1 asset in disguise. An asset carrying a link7 inertia, the rotated base_link
    frame, or a gripper model is refused here with every reason named.

    Args:
        v1_asset: The parsed v1 seed asset; must carry v1 provenance.
        converter: The v1->v2 joint-frame map for this arm.
        v2_provenance: The provenance to stamp on the converted asset; must be robot_version
            "2.0".

    Returns:
        (LoadedDynamicsAsset) The converted, v2-provenanced asset.

    Raises:
        DynamicsConversionError: On an unconvertible item, missing v1 provenance, or a non-v2
            target provenance.
    """
    if not isinstance(v1_asset, dict):
        raise DynamicsConversionError(f"v1 asset must be a mapping, got {type(v1_asset).__name__}")
    if PROVENANCE_KEY not in v1_asset:
        raise DynamicsConversionError(
            "v1 asset carries no provenance; nothing may be converted without a recorded origin "
            "(FR-SAF-067)"
        )
    # Validate the source stamp exists and is well-formed. Its version is expected to be v1, so
    # it is not run through the strict gate — the strict gate applies to the converted output.
    Provenance.from_mapping(v1_asset[PROVENANCE_KEY], "v1 asset")

    if not v2_provenance.is_v2():
        raise DynamicsConversionError(
            f"converted-asset provenance must be robot_version {ROBOT_VERSION_V2!r}, got "
            f"{v2_provenance.robot_version!r}: a conversion that keeps the v1 version tag would "
            "re-enter the strict gate as a v1 asset (FR-SAF-067)"
        )

    refusals = unconvertible_items(v1_asset)
    if refusals:
        detail = "; ".join(f"{item.item}: {item.reason}" for item in refusals)
        raise DynamicsConversionError(
            f"v1 asset has {len(refusals)} unconvertible item(s), load refused (FR-SAF-033): "
            f"{detail}"
        )

    converted = _convert_joint_frame_fields(v1_asset, converter)
    converted[PROVENANCE_KEY] = v2_provenance.to_dict()
    return load_safety_params(converted, strict=True)


def _convert_joint_frame_fields(
    v1_asset: dict[str, Any], converter: JointFrameConverter
) -> dict[str, Any]:
    """Return a copy of the asset with its joint-vector fields mapped into the v2 frame.

    Angle-typed fields carry the joint2 zero shift plus axis sign; torque-typed fields carry
    the axis sign only. Every other key is copied through unchanged — friction coefficients and
    gains are frame-invariant magnitudes this converter does not rewrite (they are owned by
    WP-2B-10 / WP-2B-07).

    Args:
        v1_asset: The parsed v1 seed asset.
        converter: The v1->v2 joint-frame map for this arm.

    Returns:
        (dict[str, Any]) The frame-converted copy, provenance still the v1 stamp.

    Raises:
        DynamicsConversionError: If a present joint-vector field is the wrong width.
    """
    converted = dict(v1_asset)
    for field_name in ANGLE_VECTOR_FIELDS:
        if field_name in converted:
            converted[field_name] = list(converter.convert_angles(converted[field_name]))
    for field_name in TORQUE_VECTOR_FIELDS:
        if field_name in converted:
            converted[field_name] = list(converter.convert_torques(converted[field_name]))
    return converted
