"""What this rig's camera slots are, and which physical camera is behind each one.

Two halves, separated because they change for different reasons.

The **profile** — the stream a slot is opened at and the controls it is declared to hold — is a
property of the slot's job. A wrist camera is opened at 1920x1200@30 because that is what a wrist
view needs, and moving the camera to another USB port does not change that.

The **binding** — which physical camera answers for a slot — is a property of this bench on this
day, and it was written into the source as three port strings. That is what this module takes
out. `06` FR-CAM-004 already forbids binding a slot by enumeration index; a port path compiled
into the source is the same class of mistake one step further out, because it is an answer that
was true when someone typed it and nothing checks it since.

Discovery is the kernel's: `portpath.enumerate_capture_nodes` asks every node what port it hangs
off. What discovery cannot supply is which of two identical cameras is the left wrist — both
Arducam B0495 report the serial `Arducam_202500915_0001`, so nothing in the device separates them
and the operator's identification is the only evidence there is. That answer is persisted here,
keyed on the port, and resolved against the nodes present at each run.

This is the same shape `ops/hw/canbind` uses for the two arms, and for the same reason: the arms
are indistinguishable on the bus, so a human establishes the mapping once and the file carries it
forward. It is deliberately a second implementation rather than a shared one — two cases do not
tell you which parts are general, and the failure modes differ (a camera can be covered; an arm
has to be moved).
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from backend.camera.controls import CameraControl
from backend.camera.portpath import CaptureNode
from backend.camera.v4l2_source import CaptureFormat

# The file the operator's identification lives in, beside the CAN channel record.
BINDING_FILENAME = "camera_binding.json"

# The document's shape. A version is carried so a reader meeting a shape it does not know refuses
# instead of finding no slots and reporting an empty rig, which reads like a rig with no cameras.
BINDING_VERSION = 1
FIELD_VERSION = "version"
FIELD_SLOTS = "slots"


@dataclass(frozen=True)
class SlotProfile:
    """How a slot is opened, independent of which camera is behind it.

    Attributes:
        capture_format: The stream to open it at.
        declared_controls: The controls it is declared to hold. Empty for a camera whose ranges
            this project has not measured — the ZED-M is one, and a declared value it silently
            clamps is worse than no declaration.
    """

    capture_format: CaptureFormat
    declared_controls: tuple[CameraControl, ...]


class CameraBindingError(Exception):
    """The slot-to-camera record is missing, malformed, or does not match what is plugged in."""


@dataclass(frozen=True)
class CameraBinding:
    """The operator's answer: slot -> the port path it was physically confirmed on.

    Attributes:
        slots: Slot name to `CaptureNode.port_path`. A slot absent from the map was never bound.
    """

    slots: Mapping[str, str]

    def port_for(self, slot: str) -> str | None:
        """Return the port bound to a slot, or None when it was never bound."""
        return self.slots.get(slot)


@dataclass(frozen=True)
class BindingCheck:
    """What matched between a stored binding and the capture nodes present.

    Attributes:
        resolved: Slots whose bound port is present, mapped to the node to open.
        missing: Slots whose bound port is absent, in the profile's order.
        unbound_ports: Ports present that no slot claims, sorted.
    """

    resolved: Mapping[str, CaptureNode]
    missing: tuple[str, ...]
    unbound_ports: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """Whether every slot in the profile set resolved."""
        return not self.missing


def binding_path(directory: Path) -> Path:
    """Return the camera binding file path under a directory."""
    return directory / BINDING_FILENAME


def check_binding(
    binding: CameraBinding, slots: Sequence[str], nodes: Sequence[CaptureNode]
) -> BindingCheck:
    """Compare a stored binding against the capture nodes enumerated now.

    Reports rather than raises, so a caller can show the operator the whole picture at once —
    which slot went missing and which camera is plugged in that nothing claims are usually the
    two halves of one move, and naming only the first sends them looking for a dead camera.

    Args:
        binding: The stored slot-to-port answer.
        slots: The slot names this rig expects, in the order to report them.
        nodes: The capture nodes present right now.

    Returns:
        (BindingCheck) What resolved, what went missing, and what is present but unclaimed.
    """
    by_port = {node.port_path: node for node in nodes}
    resolved: dict[str, CaptureNode] = {}
    missing: list[str] = []
    for slot in slots:
        port = binding.port_for(slot)
        node = None if port is None else by_port.get(port)
        if node is None:
            missing.append(slot)
        else:
            resolved[slot] = node
    claimed = set(binding.slots.values())
    unbound = tuple(sorted(port for port in by_port if port not in claimed))
    return BindingCheck(resolved=resolved, missing=tuple(missing), unbound_ports=unbound)


def resolve_slots(
    binding: CameraBinding, slots: Sequence[str], nodes: Sequence[CaptureNode]
) -> dict[str, CaptureNode]:
    """Resolve every slot to the node to open now, or refuse and say what is wrong.

    Args:
        binding: The stored slot-to-port answer.
        slots: The slot names this rig expects.
        nodes: The capture nodes present right now.

    Returns:
        (dict) Slot name to the node to open, for every slot.

    Raises:
        CameraBindingError: If any slot's camera is absent. Refused rather than skipped: this
            set is what `PG-CAM-001` measures, and a run over two of three answers a question
            nobody asked. The tolerant path — a dead camera warned about and skipped so the arm
            keeps moving — is `backend/sensing/connect`'s.
    """
    check = check_binding(binding, slots, nodes)
    if check.ok:
        return dict(check.resolved)
    present = ", ".join(f"{node.card} at {node.port_path}" for node in nodes) or "nothing"
    raise CameraBindingError(
        f"no camera is bound and present for {', '.join(check.missing)}. "
        f"Capture nodes present: {present}. "
        f"Ports present that no slot claims: {', '.join(check.unbound_ports) or 'none'}. "
        "A camera moved ports, or one is not enumerating. Re-run `oa-camcap --bind`; do not "
        "guess, because the wrist pair reports one serial between the two of them."
    )


def load_binding(path: Path) -> CameraBinding:
    """Read and validate a stored binding.

    Args:
        path: The binding file.

    Returns:
        (CameraBinding) The stored slot-to-port answer.

    Raises:
        CameraBindingError: If the file is absent, unparseable, of an unknown version, or holds
            anything but a slot-to-string map.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as absent:
        raise CameraBindingError(
            f"no camera binding at {path}. Run `oa-camcap --bind` to record which camera is in "
            "which slot; the wrist pair reports one serial, so this cannot be derived."
        ) from absent
    except (OSError, ValueError) as unreadable:
        raise CameraBindingError(f"camera binding at {path} is unreadable: {unreadable}") from (
            unreadable
        )
    if not isinstance(document, dict):
        raise CameraBindingError(f"camera binding at {path} must hold an object")
    version = document.get(FIELD_VERSION)
    if version != BINDING_VERSION:
        raise CameraBindingError(
            f"camera binding at {path} is version {version!r}, not {BINDING_VERSION}. "
            "Re-run `oa-camcap --bind`."
        )
    slots = document.get(FIELD_SLOTS)
    if not isinstance(slots, dict) or not all(
        isinstance(key, str) and isinstance(value, str) and value for key, value in slots.items()
    ):
        raise CameraBindingError(
            f"camera binding at {path} must hold a slot-to-port map of non-empty strings"
        )
    return CameraBinding(slots=dict(slots))


def save_binding(path: Path, binding: CameraBinding) -> None:
    """Write the binding atomically: temp file, fsync, rename, fsync the directory.

    A torn write leaves the rig with a half-read map of which camera is which, and that failure
    surfaces as a left wrist view labelled right rather than as a parse error.
    """
    body = json.dumps(
        {FIELD_VERSION: BINDING_VERSION, FIELD_SLOTS: dict(sorted(binding.slots.items()))},
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
        temp_path.replace(path)
        _fsync_dir(path.parent)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _fsync_dir(directory: Path) -> None:
    """Fsync a directory so a rename into it survives a crash."""
    fd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


__all__ = [
    "BINDING_FILENAME",
    "BINDING_VERSION",
    "BindingCheck",
    "CameraBinding",
    "CameraBindingError",
    "SlotProfile",
    "binding_path",
    "check_binding",
    "load_binding",
    "resolve_slots",
    "save_binding",
]
