"""Gripper (J8) endpoint capture + sign-mirror schema (WP-2A-08, FR-MAN-016/017).

The gripper mapping is an endpoint-rad capture with a norm[0,1] linear interpolation
and a per-unit force cap — never a physical force unit, never a load-cell measurement
(FR-MAN-016, FR-SAF-024b). The cross-arm invariant this package owns, which a
single-arm calibration cannot state, is the sign mirror `left = [-hi_right, -lo_right]`
(FR-MAN-017, FR-TEL-059): a config that violates it is refused at load, because an
un-mirrored left arm silently clips its open command to zero and never opens.

The public surface, in the order a capture flows through it:

* `norm_map` — the norm[0,1] <-> native-rad linear map.
* `schema` — the record shapes and the load-time invariants (the sign mirror lives
  here); `GripperEndpointCapture.from_calibration` bridges to the CTR-CAL endpoints.
* `posforce` — the speed cap clamped to the DM4310 register V_MAX and the per-unit
  force cap; `labels` holds the user-facing strings (per-unit only).
* `capture` — the operator capture flow (the physical read is the deferred stage).
* `persistence` — the atomic persist-then-swap of the record.
* `reverify` — the real-fixture re-verification hook for the deferred capture.
"""

from __future__ import annotations

from backend.gripper_endpoint.capture import build_capture, build_mirror_record
from backend.gripper_endpoint.constants import (
    GRIPPER_SPEED_CAP_RAD_S,
    SIDE_LEFT,
    SIDE_RIGHT,
    SIDES,
    TORQUE_PU_MAX,
    TORQUE_PU_MIN,
)
from backend.gripper_endpoint.errors import GripperConfigError
from backend.gripper_endpoint.norm_map import clamp01, norm_to_rad, rad_to_norm
from backend.gripper_endpoint.persistence import (
    gripper_record_path_for,
    load_gripper_record,
    save_gripper_record,
)
from backend.gripper_endpoint.posforce import (
    clamp_speed_rad_s,
    format_force_status,
    format_speed_status,
    speed_was_clamped,
    validate_torque_pu,
)
from backend.gripper_endpoint.reverify import (
    FIXTURE_ENV_VAR,
    ReverifyResult,
    fixture_dir_from_env,
    reverify_from_fixture,
)
from backend.gripper_endpoint.schema import (
    GripperEndpointCapture,
    GripperLimits,
    GripperMirrorRecord,
    mirror_limits,
)

__all__ = [
    "FIXTURE_ENV_VAR",
    "GRIPPER_SPEED_CAP_RAD_S",
    "SIDES",
    "SIDE_LEFT",
    "SIDE_RIGHT",
    "TORQUE_PU_MAX",
    "TORQUE_PU_MIN",
    "GripperConfigError",
    "GripperEndpointCapture",
    "GripperLimits",
    "GripperMirrorRecord",
    "ReverifyResult",
    "build_capture",
    "build_mirror_record",
    "clamp01",
    "clamp_speed_rad_s",
    "fixture_dir_from_env",
    "format_force_status",
    "format_speed_status",
    "gripper_record_path_for",
    "load_gripper_record",
    "mirror_limits",
    "norm_to_rad",
    "rad_to_norm",
    "reverify_from_fixture",
    "save_gripper_record",
    "speed_was_clamped",
    "validate_torque_pu",
]
