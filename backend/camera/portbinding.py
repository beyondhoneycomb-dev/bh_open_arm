"""Which camera fills which slot, decided once by the operator against a preview.

`06` FR-CAM-004 binds a slot by a stable identifier and never by enumeration index. Its named
webcam mechanism — a udev symlink keyed on serial — cannot run on this rig's wrist pair: both
Arducam B0495 ship the serial `Arducam_202500915_0001`, so udev writes one `by-id` entry and
the second camera has no stable name to bind to. FR-CAM-085 records that exact hazard and
files serial-burning as priority C, not the canonical contract.

The identifier used instead is the port the kernel reports (`backend.camera.portpath`), and
the way a slot is assigned to one is the operator looking at a frame from each camera and
saying which is which. Nothing readable from the device settles it — the two wrist cameras are
the same model with the same serial at the same resolution, so a scan can only ever say "there
are two". The same shape as the CAN channel binding, and for the same reason.

What is persisted is that answer keyed to the port it was confirmed on. The port moves when
the operator moves the plug, and this module refuses rather than follows: a binding that
silently re-resolves onto whichever camera is present now is how the right wrist's frames end
up recorded as the left wrist's.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.camera.portpath import CaptureNode, assert_ports_distinguish

BINDING_FILENAME = "camera_binding.json"
BINDING_VERSION = 1

FIELD_VERSION = "version"
FIELD_SLOTS = "slots"


class CameraBindingError(Exception):
    """A camera binding cannot be trusted for the cameras actually present."""


@dataclass(frozen=True)
class CameraBinding:
    """The operator's answer: slot -> the port it was confirmed on.

    Attributes:
        slots: Slot name to `CaptureNode.port_path`. A slot absent from the map was never bound;
            it is not bound to a placeholder, because a placeholder opens a camera.
    """

    slots: dict[str, str]

    def port_for(self, slot: str) -> str | None:
        """Return the port bound to a slot, or None when it was never bound."""
        return self.slots.get(slot)

    def node_for(self, slot: str, present: Sequence[CaptureNode]) -> CaptureNode:
        """Resolve a slot to the camera to open right now.

        Args:
            slot: The slot to resolve.
            present: The capture nodes enumerated this run.

        Returns:
            (CaptureNode) The camera on the bound port. Its `/dev/videoN` number may differ
            from the one seen when the binding was recorded — that is why the port is the key.

        Raises:
            CameraBindingError: When the slot was never bound, or its port carries no camera
                now. Both refuse rather than fall back to "the first camera", which is
                indistinguishable from the right answer until somebody reviews the footage.
        """
        port = self.port_for(slot)
        if port is None:
            raise CameraBindingError(
                f"slot {slot!r} has no bound camera; run the binding procedure first"
            )
        assert_ports_distinguish(present)
        for node in present:
            if node.port_path == port:
                return node
        seen = ", ".join(sorted(node.port_path for node in present)) or "nothing"
        raise CameraBindingError(
            f"slot {slot!r} was bound to port {port!r}, which carries no camera now; present "
            f"ports are {seen}. The camera was unplugged or moved. Re-bind against a preview — "
            "the wrist cameras are one model with one serial, so nothing on the device says "
            "which arm it is looking at (06 FR-CAM-004, FR-CAM-085)"
        )


@dataclass(frozen=True)
class BindingCheck:
    """What changed between a stored binding and the cameras present.

    Attributes:
        resolved: Slots whose bound port carries a camera, mapped to its node.
        missing: Slots whose bound port carries nothing.
        unbound_ports: Ports present that no slot claims.
    """

    resolved: dict[str, CaptureNode]
    missing: tuple[str, ...]
    unbound_ports: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """Whether every bound slot resolved. An unclaimed camera is not a failure."""
        return not self.missing


def check_binding(binding: CameraBinding, present: Sequence[CaptureNode]) -> BindingCheck:
    """Compare a stored binding against the cameras enumerated now.

    Args:
        binding: The stored slot-to-port answer.
        present: The capture nodes this host exposes right now.

    Returns:
        (BindingCheck) What resolved, what went missing, and what is present but unclaimed.

    Raises:
        AmbiguousCameraPortError: If two present cameras report one port, so no comparison
            against them means anything.
    """
    assert_ports_distinguish(present)
    by_port = {node.port_path: node for node in present}
    resolved: dict[str, CaptureNode] = {}
    missing: list[str] = []
    for slot, port in binding.slots.items():
        node = by_port.get(port)
        if node is None:
            missing.append(slot)
        else:
            resolved[slot] = node
    claimed = set(binding.slots.values())
    unbound = tuple(sorted(port for port in by_port if port not in claimed))
    return BindingCheck(resolved=resolved, missing=tuple(sorted(missing)), unbound_ports=unbound)


def binding_from_document(document: Mapping[str, Any]) -> CameraBinding:
    """Build a binding from a loaded mapping.

    Args:
        document: The parsed binding document.

    Returns:
        (CameraBinding) The stored answer.

    Raises:
        CameraBindingError: If the version is not one this code wrote, or a slot names
            something other than a port string. A slot bound to an int is the enumeration
            index FR-CAM-004 refuses, and it must not be coerced into a key.
    """
    version = document.get(FIELD_VERSION)
    if version != BINDING_VERSION:
        raise CameraBindingError(
            f"camera binding is version {version!r}, not {BINDING_VERSION}; it was written by "
            "different code and the slot names may not mean the same cameras"
        )
    raw = document.get(FIELD_SLOTS)
    if not isinstance(raw, Mapping):
        raise CameraBindingError(f"camera binding has no {FIELD_SLOTS!r} map")
    slots: dict[str, str] = {}
    for slot, port in raw.items():
        if isinstance(port, bool) or not isinstance(port, str) or not port.strip():
            raise CameraBindingError(
                f"slot {slot!r} is bound to {port!r}, which is not a port path; a slot bound to "
                "an index moves to another camera on the next re-plug (06 FR-CAM-004)"
            )
        slots[str(slot)] = port.strip()
    return CameraBinding(slots=slots)


def binding_path(directory: Path) -> Path:
    """Return the binding file path under a directory."""
    return directory / BINDING_FILENAME


def load_binding(path: Path) -> CameraBinding | None:
    """Read a stored binding, or None when none was ever written.

    Args:
        path: The binding file.

    Returns:
        (CameraBinding | None) The stored answer, or None when the file is absent.

    Raises:
        CameraBindingError: If the file exists and cannot be read as a binding. A corrupt
            record is refused rather than treated as absent, because "absent" prompts a rebind
            and "corrupt" means something already went wrong that a rebind would paper over.
    """
    if not path.exists():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as failure:
        raise CameraBindingError(f"camera binding at {path} cannot be read: {failure}") from failure
    if not isinstance(document, Mapping):
        raise CameraBindingError(f"camera binding at {path} is not an object")
    return binding_from_document(document)


def save_binding(path: Path, binding: CameraBinding) -> None:
    """Write the binding atomically: temp file, fsync, rename, fsync the directory.

    A torn write leaves the rig with a half-read map of which camera is which, and that
    surfaces as footage labelled with the wrong arm rather than as a parse error.
    """
    body = json.dumps(
        {
            FIELD_VERSION: BINDING_VERSION,
            FIELD_SLOTS: dict(sorted(binding.slots.items())),
        },
        indent=2,
        sort_keys=True,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    handle_fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            handle.write(body + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)  # noqa: PTH105 — atomic rename primitive
        _fsync_dir(path.parent)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _fsync_dir(directory: Path) -> None:
    """Fsync a directory so a rename into it survives a crash."""
    descriptor = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
