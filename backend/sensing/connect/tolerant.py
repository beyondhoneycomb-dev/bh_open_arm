"""Tolerant camera connect: open each camera alone, skip the dead ones, keep the arm.

`06` §2.12 / `FR-CAM-084` is the contract: cameras open independently, a dead one is
warned and skipped, and none of that fails the arm's connect or motion — only
observation and recording degrade. This module is that orchestration over the frozen
synthetic fixture, reusing three WP-0B-08 pieces rather than restating them:

* `backend.camera.binding` — a slot binds by a stable serial or udev symlink, never an
  enumeration index (`FR-CAM-004`); an index-based spec raises before it can pin a
  moving slot. That rejection is a configuration error, so it propagates; a runtime
  camera death is the thing that is tolerated, not a malformed binding.
* `backend.camera.bandwidth` — the `06` §2.9 bandwidth formula, reused to decide which
  profiles a USB2-fallback camera may not select (`FR-CAM-003`). Two sources of truth
  for that formula would be the worst outcome, so this imports it.
* `contracts.camera_registry` / `contracts.prim` — the `CTR-CAM@v1` camera set and the
  `CTR-PRIM@v1` error envelope, consumed by reference.

What does not run here is real enumeration — real serials, real link speeds, a real
first-frame grab — which needs hardware this host lacks. That boundary and its
re-verification hook live in `deferred.py`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from backend.camera.bandwidth import profile_bandwidth_mbps
from backend.camera.binding import BindingError, parse_binding_spec
from backend.camera.descriptor import CameraDescriptor, LinkSpeed
from backend.sensing.connect.constants import DEFAULT_PROBE_DEPTH, USB2_NOMINAL_MBPS
from backend.sensing.connect.outcome import (
    BlockedProfile,
    CameraConnectOutcome,
    ConnectReport,
    ConnectStatus,
    SkipReason,
)
from backend.sensing.connect.probe import LiveFrameSource
from contracts.camera_registry import CameraRegistry, camera_error
from contracts.prim import REGISTRY, ErrorEnvelope, codes


def _disconnect_error(slot: str, detail: str) -> ErrorEnvelope:
    """Wrap the registered `OA-CAM-001` disconnect code for a device-side death.

    A skipped-because-dead camera is a real ERROR-severity condition for *that*
    camera (`14` §2.10, `OA-CAM-001`); its non-fatality to the arm is a separate
    axis carried by `ConnectStatus.SKIPPED`, not by lowering the code's severity.

    Args:
        slot: The slot key that died.
        detail: The human-readable reason to attach.

    Returns:
        (ErrorEnvelope) The shared `CTR-PRIM@v1` envelope for the disconnect.
    """
    return camera_error(REGISTRY.get(codes.OA_CAM_001), f"camera slot {slot!r}: {detail}")


def _usb2_findings(
    slot: str,
    descriptor: CameraDescriptor,
    usb2_budget_mbps: float,
) -> tuple[tuple[str, ...], tuple[BlockedProfile, ...]]:
    """Compute the USB2-fallback warning and refused profiles for an opened camera.

    `FR-CAM-003`: a camera that fell back to USB2 is flagged, and any profile whose
    `06` §2.9 bandwidth overruns the (caller-supplied) USB2 budget is refused. The
    camera still opens; only the too-heavy profile is blocked.

    Args:
        slot: The camera's slot key.
        descriptor: The enumerated camera.
        usb2_budget_mbps: The budget a profile may not exceed on a USB2 link.

    Returns:
        (tuple) `(warnings, blocked_profiles)`.
    """
    warnings: list[str] = [
        f"slot {slot!r} negotiated a USB2 link (FR-CAM-003 fallback); "
        "bandwidth-exceeding profiles are refused"
    ]
    blocked: list[BlockedProfile] = []
    for profile in descriptor.profiles:
        required = profile_bandwidth_mbps(profile)
        if required > usb2_budget_mbps:
            blocked.append(
                BlockedProfile(
                    profile=profile, required_mbps=required, budget_mbps=usb2_budget_mbps
                )
            )
            warnings.append(
                f"slot {slot!r} profile {profile.width}x{profile.height}@{profile.fps} "
                f"{profile.stream_kind.value} needs {required:.1f} Mbps > "
                f"{usb2_budget_mbps:.1f} Mbps USB2 budget — blocked"
            )
    return tuple(warnings), tuple(blocked)


def _opened_outcome(
    slot: str,
    serial: str,
    descriptor: CameraDescriptor,
    usb2_budget_mbps: float,
) -> CameraConnectOutcome:
    """Build the outcome for a camera that opened and delivered a frame."""
    warnings: tuple[str, ...] = ()
    blocked: tuple[BlockedProfile, ...] = ()
    if descriptor.link_speed is LinkSpeed.USB2:
        warnings, blocked = _usb2_findings(slot, descriptor, usb2_budget_mbps)
    return CameraConnectOutcome(
        slot=slot,
        serial=serial,
        status=ConnectStatus.OPENED,
        reason=None,
        link_speed=descriptor.link_speed,
        error=None,
        warnings=warnings,
        blocked_profiles=blocked,
    )


def _connect_one(
    slot: str,
    serial: str | None,
    descriptor: CameraDescriptor | None,
    probe: LiveFrameSource | None,
    probe_depth: int,
    usb2_budget_mbps: float,
) -> CameraConnectOutcome:
    """Connect a single camera tolerantly, returning its disposition.

    The four skip reasons are the tolerated conditions of `06` §4.2, each warned and
    non-fatal: no serial bound (UNBOUND), the serial absent from the bus
    (DISCONNECTED), no capture handle (OPEN_FAILED), or a handle with no frame in the
    probe window (NO_FRAME). Any exception the probe raises is itself an open failure,
    caught here rather than propagated — propagating is the one thing tolerance forbids.

    Args:
        slot: The camera's slot key.
        serial: The serial it is bound to, or None when UNBOUND.
        descriptor: The enumerated camera, or None when the serial is off the bus.
        probe: The liveness source, or None when no handle could be opened.
        probe_depth: How many frame indices to look back for a live frame.
        usb2_budget_mbps: The USB2 profile-block budget.

    Returns:
        (CameraConnectOutcome) The camera's disposition.
    """
    if serial is None:
        return _skip(
            slot,
            None,
            SkipReason.UNBOUND,
            None,
            error=None,
            warning=f"slot {slot!r} has no serial bound; skipped (UNBOUND)",
        )
    if descriptor is None:
        return _skip(
            slot,
            serial,
            SkipReason.DISCONNECTED,
            None,
            error=_disconnect_error(slot, f"serial {serial!r} is not on the enumerated bus"),
            warning=f"slot {slot!r} serial {serial!r} not enumerated; skipped (DISCONNECTED)",
        )
    if probe is None:
        return _skip(
            slot,
            serial,
            SkipReason.OPEN_FAILED,
            descriptor.link_speed,
            error=_disconnect_error(slot, "no capture handle could be opened"),
            warning=f"slot {slot!r} could not be opened; skipped (OPEN_FAILED)",
        )
    try:
        frame = probe.read_latest(probe_depth)
    except Exception as failure:  # tolerance: any grab failure is a dead camera, not a crash
        return _skip(
            slot,
            serial,
            SkipReason.OPEN_FAILED,
            descriptor.link_speed,
            error=_disconnect_error(slot, f"open raised: {failure}"),
            warning=f"slot {slot!r} raised on open; skipped (OPEN_FAILED)",
        )
    if frame is None:
        return _skip(
            slot,
            serial,
            SkipReason.NO_FRAME,
            descriptor.link_speed,
            error=_disconnect_error(slot, "no frame arrived within the probe window"),
            warning=f"slot {slot!r} delivered no frame; skipped (NO_FRAME)",
        )
    return _opened_outcome(slot, serial, descriptor, usb2_budget_mbps)


def _skip(
    slot: str,
    serial: str | None,
    reason: SkipReason,
    link_speed: LinkSpeed | None,
    error: ErrorEnvelope | None,
    warning: str,
) -> CameraConnectOutcome:
    """Build a skipped outcome — the tolerant, non-fatal disposition."""
    return CameraConnectOutcome(
        slot=slot,
        serial=serial,
        status=ConnectStatus.SKIPPED,
        reason=reason,
        link_speed=link_speed,
        error=error,
        warnings=(warning,),
        blocked_profiles=(),
    )


def tolerant_connect(
    registry: CameraRegistry,
    binding_spec: Mapping[str, object],
    descriptors: Sequence[CameraDescriptor],
    probes: Mapping[str, LiveFrameSource],
    *,
    probe_depth: int = DEFAULT_PROBE_DEPTH,
    usb2_budget_mbps: float = USB2_NOMINAL_MBPS,
) -> ConnectReport:
    """Connect a registered camera set tolerantly; a dead camera never blocks the arm.

    Each registered camera is opened on its own: bound by serial (`FR-CAM-004`, index
    rejected), matched to an enumerated descriptor, and probed for a first frame. A
    camera that is unbound, off the bus, unopenable, or frameless is warned and
    skipped; the others and the arm proceed (`FR-CAM-084`). A USB2-fallback camera
    opens but is flagged and has its over-budget profiles refused (`FR-CAM-003`).

    Args:
        registry: The `CTR-CAM@v1` registered cameras — the logical camera set.
        binding_spec: Slot key to intended serial/udev symlink. An enumeration-index
            binding is a configuration error and raises.
        descriptors: The enumerated cameras (real or synthetic-fixture descriptors).
        probes: Slot key to its liveness source; a slot absent here opened no handle.
        probe_depth: Frame indices to look back for a live frame at open.
        usb2_budget_mbps: Budget a profile may not exceed on a USB2 fallback link.

    Returns:
        (ConnectReport) Per-camera outcomes and the arm-may-proceed verdict.

    Raises:
        IndexBindingError: If any binding pins a slot by enumeration index.
        BindingError: If a binding names a slot no camera is registered under.
    """
    bindings = parse_binding_spec(binding_spec)
    for binding in bindings:
        if binding.slot not in registry.cameras:
            raise BindingError(
                f"slot {binding.slot!r} is bound but no camera is registered under it"
            )

    serial_by_slot = {binding.slot: binding.serial for binding in bindings}
    descriptor_by_serial = {descriptor.serial: descriptor for descriptor in descriptors}

    outcomes = tuple(
        _connect_one(
            slot=slot,
            serial=serial_by_slot.get(slot),
            descriptor=descriptor_by_serial.get(serial_by_slot.get(slot, "")),
            probe=probes.get(slot),
            probe_depth=probe_depth,
            usb2_budget_mbps=usb2_budget_mbps,
        )
        for slot in sorted(registry.cameras)
    )
    # The tolerant connect contributes nothing to `blocking_failures`: a camera death
    # is never an arm failure (`FR-CAM-084`). The empty tuple is the invariant made
    # observable — a test asserts it stays empty after a camera is killed.
    return ConnectReport(outcomes=outcomes, blocking_failures=())
