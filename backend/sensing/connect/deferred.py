"""Real-enumeration boundary and its re-verification hook (`02a` §4.1).

The tolerant connect, the serial binding and the USB2 profile block all run here on
synthetic-fixture data. What cannot run on this host is *real enumeration* — real
serials, real negotiated link speeds, a real first-frame grab — because there are no
cameras. This module is the honest boundary: `real_connect_supported` reports whether
the enumeration backends exist (delegating to WP-0B-08, no second probe), so a bound
test skips *with a reason* rather than fabricating a descriptor.

`reconnect_from_fixture` is what the deferral is required to ship: the moment a
directory of real captured output is supplied, it rebuilds the camera set from the
captured descriptors and re-runs the identical `tolerant_connect` — binding, USB2
fallback, bandwidth block — against the real bytes. Recorded per-slot liveness drives
the same skip/open path, so no code is re-implemented for hardware.

The fixture directory holds:
- `descriptors.json` — enumerated camera descriptors (required),
- `binding.json`     — `{slot: serial}` to bind (required),
- `liveness.json`    — `{slot: bool}` recording which slots delivered a frame (optional;
  a slot omitted is taken as live, since it enumerated),
- `expected.json`    — `{"usb2_budget_mbps": float}` budget override (optional).
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from backend.camera.descriptor import CameraDescriptor, StreamKind
from backend.camera.enumerate_hw import real_enumeration_supported
from backend.camera.reverify import load_descriptors
from backend.sensing.connect.constants import (
    BINDING_FILENAME,
    DESCRIPTORS_FILENAME,
    EXPECTED_FILENAME,
    LIVENESS_FILENAME,
    REAL_FIXTURE_ENV_VAR,
    USB2_NOMINAL_MBPS,
)
from backend.sensing.connect.outcome import ConnectReport
from backend.sensing.connect.probe import LiveFrameSource, RecordedLiveness
from backend.sensing.connect.tolerant import tolerant_connect
from contracts.camera_registry import CameraRegistry, CameraSpec
from contracts.prim import REQUIRED_FRAME_TYPE, CameraSlotKey, FrameType


def real_connect_supported() -> tuple[bool, str]:
    """Report whether a real tolerant connect can run here, and why not when it cannot.

    Real enumeration needs the RealSense/udev backends WP-0B-08 already probes for;
    this reuses that verdict rather than probing again, so the two harnesses agree on
    what "no hardware" means.

    Returns:
        (tuple[bool, str]) `(supported, reason)`; reason is empty when supported.
    """
    return real_enumeration_supported()


def fixture_dir_from_env() -> Path | None:
    """Return the real-capture directory named by the environment, if set and present.

    A rig points the deferred hook at its captures through `REAL_FIXTURE_ENV_VAR`; an
    unset or absent path returns None so a bound test skips rather than fabricating one.

    Returns:
        (Path | None) The fixture directory, or None when unset or missing.
    """
    raw = os.environ.get(REAL_FIXTURE_ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _capabilities_for(descriptor: CameraDescriptor | None) -> frozenset[FrameType]:
    """Infer a camera's capability set from its enumerated profiles.

    RGB is always present (`REQUIRED_FRAME_TYPE`); depth is added when the descriptor
    carries a depth stream. A serial that did not enumerate (a dead camera) has no
    descriptor, so it registers as RGB-only — enough to bind and skip.

    Args:
        descriptor: The enumerated camera, or None when off the bus.

    Returns:
        (frozenset[FrameType]) The capability set for the registered camera.
    """
    capabilities = {REQUIRED_FRAME_TYPE}
    if descriptor is not None and any(
        profile.stream_kind is StreamKind.DEPTH for profile in descriptor.profiles
    ):
        capabilities.add(FrameType.DEPTH)
    return frozenset(capabilities)


def _registry_from(
    binding_spec: Mapping[str, str],
    descriptors: tuple[CameraDescriptor, ...],
) -> CameraRegistry:
    """Register one `CTR-CAM@v1` camera per bound slot, keyed by the slot's own grammar.

    Args:
        binding_spec: Slot key to serial from the captured binding.
        descriptors: The enumerated cameras.

    Returns:
        (CameraRegistry) A registry whose slots are exactly the bound cameras.
    """
    by_serial = {descriptor.serial: descriptor for descriptor in descriptors}
    registry = CameraRegistry()
    for slot, serial in sorted(binding_spec.items()):
        registry.register(
            CameraSpec(
                slot=CameraSlotKey(slot),
                capabilities=_capabilities_for(by_serial.get(serial)),
                width=None,
                height=None,
                fps=None,
            )
        )
    return registry


def reconnect_from_fixture(fixture_dir: Path) -> ConnectReport:
    """Re-run the tolerant connect against a directory of real captured output.

    Every step is the one the synthetic tests exercise, pointed at real bytes — the
    point of the hook is that no path is re-implemented for hardware.

    Args:
        fixture_dir: Directory of captured JSON (see the module docstring).

    Returns:
        (ConnectReport) The connect report derived from the real capture.

    Raises:
        FileNotFoundError: If `descriptors.json` or `binding.json` is missing.
    """
    descriptors_path = fixture_dir / DESCRIPTORS_FILENAME
    if not descriptors_path.is_file():
        raise FileNotFoundError(f"missing {DESCRIPTORS_FILENAME} in {fixture_dir}")
    binding_path = fixture_dir / BINDING_FILENAME
    if not binding_path.is_file():
        raise FileNotFoundError(f"missing {BINDING_FILENAME} in {fixture_dir}")

    descriptors = load_descriptors(descriptors_path)
    binding_spec = {str(slot): str(serial) for slot, serial in _load_json(binding_path).items()}

    liveness: dict[str, bool] = {}
    liveness_path = fixture_dir / LIVENESS_FILENAME
    if liveness_path.is_file():
        liveness = {str(slot): bool(live) for slot, live in _load_json(liveness_path).items()}

    usb2_budget_mbps: float = USB2_NOMINAL_MBPS
    expected_path = fixture_dir / EXPECTED_FILENAME
    if expected_path.is_file():
        usb2_budget_mbps = float(
            _load_json(expected_path).get("usb2_budget_mbps", usb2_budget_mbps)
        )

    probes: dict[str, LiveFrameSource] = {
        slot: RecordedLiveness(slot=slot, is_live=liveness.get(slot, True)) for slot in binding_spec
    }
    registry = _registry_from(binding_spec, descriptors)
    return tolerant_connect(
        registry, binding_spec, descriptors, probes, usb2_budget_mbps=usb2_budget_mbps
    )
