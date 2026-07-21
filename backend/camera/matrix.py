"""Capability-matrix builder plus topology and capability-registry checks.

The matrix is `02a` WP-0B-08's core deliverable: one row per camera carrying
`{serial, type, model, profiles[], controller, link speed}` (`06` FR-CAM-002). Around
it sit the topology checks the same enumeration produces:

- controller membership and the "two on one controller" warning (FR-CAM-005),
- the USB2-fallback flag (FR-CAM-003).

And the `16` D-12 contract: the camera set is a *name-based registry with required /
optional capabilities*, not a rigid five-stream schema. `check_capability_registry`
verifies the required slots are satisfied and reports the optional ones — a real
profile need only cover the required subset, extra cameras live in their own names.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from backend.camera.descriptor import CameraDescriptor, LinkSpeed, StreamKind


@dataclass(frozen=True)
class CapabilityRow:
    """One camera's row in the capability matrix (`06` FR-CAM-002 columns).

    Attributes:
        serial: Stable identifier.
        camera_type: Backend type value.
        model: Model string.
        profiles: `(width, height, fps, stream_kind)` tuples of active streams.
        controller: USB controller / root hub id.
        link_speed: Negotiated link-speed value.
    """

    serial: str
    camera_type: str
    model: str
    profiles: tuple[tuple[int, int, int, str], ...]
    controller: str
    link_speed: str


def build_matrix(descriptors: Sequence[CameraDescriptor]) -> tuple[CapabilityRow, ...]:
    """Build the capability matrix, one row per camera, sorted by serial."""
    rows = [
        CapabilityRow(
            serial=d.serial,
            camera_type=d.camera_type.value,
            model=d.model,
            profiles=tuple((p.width, p.height, p.fps, p.stream_kind.value) for p in d.profiles),
            controller=d.controller,
            link_speed=d.link_speed.value,
        )
        for d in descriptors
    ]
    return tuple(sorted(rows, key=lambda r: r.serial))


def controller_membership(descriptors: Sequence[CameraDescriptor]) -> dict[str, tuple[str, ...]]:
    """Map each controller to the serials hanging off it (`06` FR-CAM-005).

    Returns:
        (dict[str, tuple[str, ...]]) Controller id to sorted serials, sorted by id.
    """
    membership: dict[str, list[str]] = {}
    for descriptor in descriptors:
        membership.setdefault(descriptor.controller, []).append(descriptor.serial)
    return {
        controller: tuple(sorted(serials)) for controller, serials in sorted(membership.items())
    }


def shared_controller_warnings(descriptors: Sequence[CameraDescriptor]) -> tuple[str, ...]:
    """Return a warning per controller carrying two or more cameras (FR-CAM-005).

    Returns:
        (tuple[str, ...]) One warning line per shared controller, sorted.
    """
    return tuple(
        f"controller {controller!r} shares {len(serials)} cameras "
        f"({', '.join(serials)}) — they contend for one link's bandwidth"
        for controller, serials in controller_membership(descriptors).items()
        if len(serials) >= 2
    )


def usb2_fallback_serials(descriptors: Sequence[CameraDescriptor]) -> tuple[str, ...]:
    """Return serials of cameras that negotiated a USB2 link (`06` FR-CAM-003).

    Returns:
        (tuple[str, ...]) Sorted serials on a USB2 link.
    """
    return tuple(sorted(d.serial for d in descriptors if d.link_speed is LinkSpeed.USB2))


@dataclass(frozen=True)
class CapabilityRequirement:
    """A named slot the registry expects, and what it must be able to stream.

    Attributes:
        name: Slot name in the registry.
        required: Whether the configuration is invalid without this slot.
        needs: Stream kinds the bound camera must provide (empty = presence only).
    """

    name: str
    required: bool
    needs: frozenset[StreamKind]


@dataclass(frozen=True)
class RegistryCheck:
    """Outcome of checking bound slots against a capability registry (`16` D-12).

    Attributes:
        satisfied: True when every required slot is present and covers its needs.
        missing_required: Required slot names absent or under-provisioned.
        present_optional: Optional slot names that were supplied.
        unexpected: Bound slots the registry does not name (allowed, reported).
    """

    satisfied: bool
    missing_required: tuple[str, ...]
    present_optional: tuple[str, ...]
    unexpected: tuple[str, ...]


def check_capability_registry(
    bound: Mapping[str, CameraDescriptor],
    requirements: Sequence[CapabilityRequirement],
) -> RegistryCheck:
    """Check bound slots against a name-based required/optional registry (D-12).

    This is the anti-rigid-schema check: presence of the *required* named slots (each
    covering its declared stream kinds) is the contract; optional and unexpected slots
    are reported, not rejected. A five-camera rig and a two-camera rig both pass if
    each supplies the required subset.

    Args:
        bound: Slot name to its resolved descriptor.
        requirements: The registry's required/optional slots.

    Returns:
        (RegistryCheck) Satisfaction plus the missing / optional / unexpected sets.
    """
    named = {requirement.name for requirement in requirements}
    missing: list[str] = []
    present_optional: list[str] = []

    for requirement in requirements:
        descriptor = bound.get(requirement.name)
        if descriptor is None:
            if requirement.required:
                missing.append(requirement.name)
            continue
        provided = {p.stream_kind for p in descriptor.profiles}
        if not requirement.needs <= provided:
            if requirement.required:
                missing.append(requirement.name)
            continue
        if not requirement.required:
            present_optional.append(requirement.name)

    unexpected = sorted(slot for slot in bound if slot not in named)
    return RegistryCheck(
        satisfied=not missing,
        missing_required=tuple(sorted(missing)),
        present_optional=tuple(sorted(present_optional)),
        unexpected=tuple(unexpected),
    )
