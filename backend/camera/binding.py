"""Serial-based slot binding, and the rejection of index-based binding (FR-CAM-004).

A slot is bound to a camera by a *stable* identifier — a RealSense serial or a webcam
udev by-id symlink — never by USB enumeration index, which LeRobot warns "may change
after rebooting or re-plugging". `02a` WP-0B-08's contract makes the rejection a hard
gate (acceptance ⑧): a binding spec that names a bare index or a `/dev/videoN` node is
refused before it can pin a slot to something that moves.

The three index shapes this refuses:
- an int value (the enumeration index itself),
- a bare-integer string (`"0"`),
- a `/dev/videoN` device node (the index wearing a path).

A `/dev/v4l/by-id/...` symlink is accepted: it encodes the device serial and is stable.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from backend.camera.descriptor import CameraDescriptor

_BARE_INDEX = re.compile(r"^\d+$")
_VIDEO_NODE = re.compile(r"^/dev/video\d+$")


class BindingError(ValueError):
    """A slot binding is malformed."""


class IndexBindingError(BindingError):
    """A slot was bound by enumeration index rather than a stable serial."""


@dataclass(frozen=True)
class SlotBinding:
    """A slot name pinned to a camera serial.

    Attributes:
        slot: Logical slot key (e.g. `wrist_rgb`).
        serial: The stable camera serial this slot binds to.
    """

    slot: str
    serial: str


def _reject_if_index(slot: str, value: object) -> str:
    """Return the serial string, or raise if the value is an enumeration index."""
    if isinstance(value, (bool, int)):
        raise IndexBindingError(f"slot {slot!r} bound by enumeration index {value!r}, not a serial")
    if not isinstance(value, str) or not value.strip():
        raise BindingError(f"slot {slot!r} has no serial")
    text = value.strip()
    if _BARE_INDEX.match(text):
        raise IndexBindingError(f"slot {slot!r} bound by bare index string {text!r}, not a serial")
    if _VIDEO_NODE.match(text):
        raise IndexBindingError(
            f"slot {slot!r} bound by device node {text!r} (an index); "
            "use a udev by-id symlink or serial"
        )
    return text


def parse_binding_spec(spec: Mapping[str, object]) -> tuple[SlotBinding, ...]:
    """Validate a slot→serial mapping, rejecting any index-based binding.

    Args:
        spec: Slot key to intended serial.

    Returns:
        (tuple[SlotBinding, ...]) Validated bindings, sorted by slot.

    Raises:
        IndexBindingError: If any slot is bound by an enumeration index.
        BindingError: If any slot has an empty or non-string serial.
    """
    bindings = [
        SlotBinding(slot=slot, serial=_reject_if_index(slot, value)) for slot, value in spec.items()
    ]
    return tuple(sorted(bindings, key=lambda b: b.slot))


def resolve_bindings(
    bindings: Sequence[SlotBinding],
    descriptors: Sequence[CameraDescriptor],
) -> dict[str, CameraDescriptor]:
    """Resolve each binding to an enumerated descriptor by matching serials.

    Args:
        bindings: Validated slot bindings.
        descriptors: Enumerated cameras.

    Returns:
        (dict[str, CameraDescriptor]) Slot key to its bound descriptor.

    Raises:
        BindingError: If a bound serial is not among the enumerated cameras.
    """
    by_serial = {d.serial: d for d in descriptors}
    resolved: dict[str, CameraDescriptor] = {}
    for binding in bindings:
        descriptor = by_serial.get(binding.serial)
        if descriptor is None:
            raise BindingError(
                f"slot {binding.slot!r} serial {binding.serial!r} matches no enumerated camera"
            )
        resolved[binding.slot] = descriptor
    return resolved
