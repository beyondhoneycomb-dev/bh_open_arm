"""Camera enumerate/measure harness (WP-0B-08).

`06` and `16` D-12 require the platform to enumerate its cameras and measure their
capabilities *before* any recording exists: what is attached, by stable serial not
enumeration index (FR-CAM-002/004); the USB bandwidth each configuration would draw
(FR-CAM-010/011); the exposure-phase sync slop between slot pairs (FR-CAM-014/015);
and the frame-drop rate (NFR-CAM-003). This package builds and measures — it records
and encodes nothing; that is Wave 3C (`PG-STO-001`).

Everything operates on `CameraDescriptor` data, never a live camera handle, so the
synthetic-fixture corpus and a real capture run through identical code. That is the
`02a` §4.1 discipline: the parts that need no hardware (the bandwidth formula, the
sync-slop distribution, the drop computer, the index-binding rejection) run and are
tested here; the parts that need real cameras (live enumeration, USB2-fallback detect,
controller membership, real drop rate, the frame-timeout reproduction) are deferred
behind `enumerate_hw` and re-run by `reverify.reverify_from_fixture` the moment a real
capture directory is supplied.

The one contract this layer enforces hard: a slot binds to a camera by *serial*, never
by enumeration index — an index-based binding spec is rejected (`binding`, ⑧).
"""

from __future__ import annotations

from backend.camera.bandwidth import (
    BandwidthVerdict,
    controller_sums_mbps,
    descriptor_bandwidth_mbps,
    evaluate_bandwidth,
    profile_bandwidth_mbps,
    total_bandwidth_mbps,
)
from backend.camera.binding import (
    BindingError,
    IndexBindingError,
    SlotBinding,
    parse_binding_spec,
    resolve_bindings,
)
from backend.camera.descriptor import (
    CameraDescriptor,
    CameraProfile,
    CameraType,
    LinkSpeed,
    SerialBindingError,
    StreamKind,
)
from backend.camera.diagnostics import (
    FRAME_TIMEOUT_ERROR,
    diagnose_frame_timeout,
    is_frame_timeout,
)
from backend.camera.droprate import (
    DropReport,
    compute_drop,
    expected_frame_count,
    frame_number_continuity,
)
from backend.camera.enumerate_hw import (
    HardwareUnavailableError,
    backend_availability,
    enumerate_cameras,
    real_enumeration_supported,
)
from backend.camera.matrix import (
    CapabilityRequirement,
    CapabilityRow,
    RegistryCheck,
    build_matrix,
    check_capability_registry,
    controller_membership,
    shared_controller_warnings,
    usb2_fallback_serials,
)
from backend.camera.reverify import (
    FIXTURE_ENV_VAR,
    ReverifyReport,
    fixture_dir_from_env,
    reverify_from_fixture,
)
from backend.camera.syncslop import (
    HistogramBin,
    SyncSlopReport,
    build_slop_reports,
    nearest_match_diffs_ns,
)

__all__ = [
    "FIXTURE_ENV_VAR",
    "FRAME_TIMEOUT_ERROR",
    "BandwidthVerdict",
    "BindingError",
    "CameraDescriptor",
    "CameraProfile",
    "CameraType",
    "CapabilityRequirement",
    "CapabilityRow",
    "DropReport",
    "HardwareUnavailableError",
    "HistogramBin",
    "IndexBindingError",
    "LinkSpeed",
    "RegistryCheck",
    "ReverifyReport",
    "SerialBindingError",
    "SlotBinding",
    "StreamKind",
    "SyncSlopReport",
    "backend_availability",
    "build_matrix",
    "build_slop_reports",
    "check_capability_registry",
    "compute_drop",
    "controller_membership",
    "controller_sums_mbps",
    "descriptor_bandwidth_mbps",
    "diagnose_frame_timeout",
    "enumerate_cameras",
    "evaluate_bandwidth",
    "expected_frame_count",
    "fixture_dir_from_env",
    "frame_number_continuity",
    "is_frame_timeout",
    "nearest_match_diffs_ns",
    "parse_binding_spec",
    "profile_bandwidth_mbps",
    "real_enumeration_supported",
    "resolve_bindings",
    "reverify_from_fixture",
    "shared_controller_warnings",
    "total_bandwidth_mbps",
    "usb2_fallback_serials",
]
