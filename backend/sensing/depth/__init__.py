"""RealSense depth path (WP-3B-03) — toggle, shape, encoding, fill rate, version gate.

`06` §2.4 makes depth an optional per-camera stream that only the RealSense
(`intelrealsense`) class emits, gated on LeRobot v0.6.0's depth record API. This
package builds the offline half of that path against the synthetic depth fixture and
consumes the frozen contracts by reference:

* `toggle` — the per-camera `use_depth` switch and the `(H, W, 1)` uint16 `{cam}_depth`
  shape (`CTR-CAM@v1`/`CTR-PRIM@v1`), so depth is never an implicit policy input.
* `encoding` — the per-camera `depth_min`/`depth_max`/`shift`/`use_log` quantiser,
  delegated to the frozen LeRobot `DepthEncoderConfig` transform (one source of truth).
* `fill_rate` — the measured/hole split of a depth frame (FR-CAM-040).
* `version_gate` — the API-presence gate that blocks collection start when depth is on
  but the runtime is < 0.6.0 (FR-CAM-083).

Live real-sensor depth and its fill rate are deferred (`PG-DEPTH-001`, no RealSense on
this host) and re-run through `reverify.reverify_from_fixture` the moment a real
capture directory is supplied.
"""

from __future__ import annotations

from backend.sensing.depth.constants import (
    DEPTH_ASYNC_READ_METHOD,
    DEPTH_LATEST_READ_METHOD,
    DEPTH_NO_MEASUREMENT_MM,
    REALSENSE_TYPE_NAME,
)
from backend.sensing.depth.encoding import (
    DepthEncodingError,
    DepthEncodingParams,
    default_depth_encoding_params,
)
from backend.sensing.depth.fill_rate import FillRateReport, compute_fill_rate
from backend.sensing.depth.reverify import (
    DepthFrameReverify,
    DepthReverifyReport,
    fixture_dir_from_env,
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
from backend.sensing.depth.version_gate import (
    DepthStartBlockedError,
    assert_depth_startable,
    depth_record_api_present,
    installed_realsense_camera_class,
    installed_runtime_supports_depth,
)

__all__ = [
    "DEPTH_ASYNC_READ_METHOD",
    "DEPTH_LATEST_READ_METHOD",
    "DEPTH_NO_MEASUREMENT_MM",
    "REALSENSE_TYPE_NAME",
    "DepthEncodingError",
    "DepthEncodingParams",
    "DepthFrameReverify",
    "DepthReverifyReport",
    "DepthShapeError",
    "DepthStartBlockedError",
    "DepthToggleError",
    "DepthToggles",
    "FillRateReport",
    "assert_depth_startable",
    "compute_fill_rate",
    "default_depth_encoding_params",
    "depth_dataset_key",
    "depth_feature_shape",
    "depth_record_api_present",
    "fixture_dir_from_env",
    "installed_realsense_camera_class",
    "installed_runtime_supports_depth",
    "resolve_depth_toggles",
    "reverify_from_fixture",
    "validate_depth_frame",
]
