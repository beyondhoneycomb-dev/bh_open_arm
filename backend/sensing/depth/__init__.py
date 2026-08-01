"""Depth path (WP-3B-03) — toggle, shape, encoding, fill rate, backend gate.

`06` §2.4 makes depth an optional per-camera stream gated on LeRobot v0.6.0's depth
record API. This package builds the offline half of that path against the synthetic
depth fixture and consumes the frozen contracts by reference:

* `constants` — the depth transport (`CTR-PRIM@v1` uint16 mm, 0 = no measurement) and,
  kept separate from it, the camera families and the LeRobot backend each one needs.
* `toggle` — the per-camera `use_depth` switch and the `(H, W, 1)` uint16 `{cam}_depth`
  shape (`CTR-CAM@v1`/`CTR-PRIM@v1`), so depth is never an implicit policy input.
* `encoding` — the per-camera `depth_min`/`depth_max`/`shift`/`use_log` quantiser,
  delegated to the frozen LeRobot `DepthEncoderConfig` transform (one source of truth).
* `fill_rate` — the measured/hole split of a depth frame (FR-CAM-040).
* `version_gate` — the backend/API gate that blocks collection start when depth is on
  but the runtime cannot record it (FR-CAM-083).
* `usb_link` — how the camera is attached, which is the one depth blocker no amount of
  software installation clears.

Everything above the `constants` split is device-agnostic: it operates on the depth
transport, which `CTR-PRIM@v1` fixes for the DEPTH frame type rather than per camera.
The device is explicit exactly where it matters — `version_gate` takes the family as a
required argument, and a real capture must name the family that produced it.

Live real-sensor depth and its fill rate are deferred (`PG-DEPTH-001`) behind three
independent blockers, which `reverify.real_depth_supported` reports together because
clearing any one of them leaves the other two: the camera fitted to this rig is a
Stereolabs ZED Mini, whose depth comes from the ZED SDK (`pyzed`, not installed); the
installed LeRobot ships no camera class for it; and it is cabled onto a full-speed link
where it publishes its HID interface and no video one — the last of which no amount of
installing clears, only a different port. `reverify.reverify_from_fixture` re-runs the
identical calculators the moment a real capture directory is supplied and judges what
comes back through `reverify.assert_capture_is_plausible`; `reverify.read_capture` is
the reading half on its own, for a capture whose numbers are the thing under study.
"""

from __future__ import annotations

from backend.sensing.depth.constants import (
    DEPTH_ASYNC_READ_METHOD,
    DEPTH_FRAME_CHANNELS,
    DEPTH_FRAME_DTYPE,
    DEPTH_LATEST_READ_METHOD,
    DEPTH_NO_MEASUREMENT_MM,
    DEPTH_SDK_MODULE,
    DEPTH_USB_ID,
    LEROBOT_DEPTH_CAMERA_CLASS,
    STEREOLABS_USB_VENDOR_ID,
    ZED_MINI_USB_PRODUCT_ID,
    DepthDevice,
)
from backend.sensing.depth.encoding import (
    DepthEncodingError,
    DepthEncodingParams,
    default_depth_encoding_params,
)
from backend.sensing.depth.fill_rate import FillRateReport, compute_fill_rate
from backend.sensing.depth.reverify import (
    MIN_REAL_CAPTURE_FILL_RATE,
    DepthFixtureError,
    DepthFrameReverify,
    DepthReverifyReport,
    assert_capture_is_plausible,
    fixture_dir_from_env,
    load_frame,
    read_capture,
    real_depth_supported,
    reverify_from_fixture,
)
from backend.sensing.depth.toggle import (
    DepthShapeError,
    DepthToggleError,
    DepthToggles,
    depth_dataset_key,
    depth_feature_shape,
    resolve_depth_toggles,
    validate_depth_frame,
)
from backend.sensing.depth.usb_link import (
    USB_SYSFS_ROOT,
    USB_VIDEO_INTERFACE_CLASS,
    UsbDepthLink,
    probe_usb_link,
)
from backend.sensing.depth.version_gate import (
    DepthApiMissingError,
    DepthBackendMissingError,
    DepthStartBlockedError,
    assert_depth_backend_exists,
    assert_depth_startable,
    depth_record_api_present,
    installed_depth_camera_class,
    installed_runtime_supports_depth,
    lerobot_backend_exists,
)

__all__ = [
    "DEPTH_ASYNC_READ_METHOD",
    "DEPTH_FRAME_CHANNELS",
    "DEPTH_FRAME_DTYPE",
    "DEPTH_LATEST_READ_METHOD",
    "DEPTH_NO_MEASUREMENT_MM",
    "DEPTH_SDK_MODULE",
    "DEPTH_USB_ID",
    "LEROBOT_DEPTH_CAMERA_CLASS",
    "MIN_REAL_CAPTURE_FILL_RATE",
    "STEREOLABS_USB_VENDOR_ID",
    "USB_SYSFS_ROOT",
    "USB_VIDEO_INTERFACE_CLASS",
    "ZED_MINI_USB_PRODUCT_ID",
    "DepthApiMissingError",
    "DepthBackendMissingError",
    "DepthDevice",
    "DepthEncodingError",
    "DepthEncodingParams",
    "DepthFixtureError",
    "DepthFrameReverify",
    "DepthReverifyReport",
    "DepthShapeError",
    "DepthStartBlockedError",
    "DepthToggleError",
    "DepthToggles",
    "FillRateReport",
    "UsbDepthLink",
    "assert_capture_is_plausible",
    "assert_depth_backend_exists",
    "assert_depth_startable",
    "compute_fill_rate",
    "default_depth_encoding_params",
    "depth_dataset_key",
    "depth_feature_shape",
    "depth_record_api_present",
    "fixture_dir_from_env",
    "installed_depth_camera_class",
    "installed_runtime_supports_depth",
    "lerobot_backend_exists",
    "load_frame",
    "probe_usb_link",
    "read_capture",
    "real_depth_supported",
    "resolve_depth_toggles",
    "reverify_from_fixture",
    "validate_depth_frame",
]
