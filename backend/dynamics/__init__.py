"""WP-2B-01 — the v1->v2 dynamics converter and provenance gate (FR-SAF-033/067, `12` §2.6).

This is the single entry point of Wave 2B: nothing downstream may compute a gravity or
friction model until a v1-derived asset has been brought into the v2 joint convention and
proven to carry v2 provenance. Two failures it exists to stop are both silent otherwise:

* The joint2 zero convention shifted by exactly +pi/2 between v1 and v2 (v1 range
  `[-1.745329, 1.745329]` -> v2 `[-0.17453, 3.3161]`). Feeding a v1 gravity model at v2
  angles without the shift swaps sin<->cos at the shoulder, the joint of largest gravity
  error, and the residual detector mis-fires forever (`12` §2.6).
* `follower.yaml` (the v1 seed) predates the first v2.0 asset by ten months and reads no
  differently from a v2 value, so provenance — not human attention — is what keeps it out of
  the v2 runtime (FR-SAF-067).

The public surface WP-2B-02 consumes:

* `converter` — the stateless joint-frame map: `JointFrameConverter.v2_default()` plus
  `convert_angles` / `invert_angles` / `convert_velocities` / `convert_torques`, and
  `convert_joint2_angle` for the single-joint core. The joint2 +pi/2 shift is
  `J2_ZERO_SHIFT_RAD`; the reference axes are `V2_JOINT_AXES`.
* `provenance` — the mandatory `{source_repo, commit_sha, path, robot_version, identified_on}`
  stamp; an incomplete stamp is unloadable.
* `asset` — the provenance-gated load (`load_safety_params`, strict by default), the explicit
  v1->v2 promotion (`convert_v1_to_v2`), and the unconvertible-item scan (`unconvertible_items`
  refusing a link7 inertia, the rotated base_link frame, or a gripper model).
"""

from __future__ import annotations

from backend.dynamics.asset import (
    LoadedDynamicsAsset,
    UnconvertibleItem,
    convert_v1_to_v2,
    load_safety_params,
    unconvertible_items,
)
from backend.dynamics.constants import (
    ARM_JOINT_COUNT,
    J2_ZERO_SHIFT_RAD,
    JOINT2_INDEX,
    PROVENANCE_FIELDS,
    ROBOT_VERSION_V1,
    ROBOT_VERSION_V2,
    V1_JOINT2_RANGE_RAD,
    V2_JOINT2_RANGE_RAD,
    V2_JOINT_AXES,
)
from backend.dynamics.converter import JointFrameConverter, convert_joint2_angle
from backend.dynamics.errors import DynamicsConversionError
from backend.dynamics.provenance import Provenance

__all__ = [
    "ARM_JOINT_COUNT",
    "J2_ZERO_SHIFT_RAD",
    "JOINT2_INDEX",
    "PROVENANCE_FIELDS",
    "ROBOT_VERSION_V1",
    "ROBOT_VERSION_V2",
    "V1_JOINT2_RANGE_RAD",
    "V2_JOINT2_RANGE_RAD",
    "V2_JOINT_AXES",
    "DynamicsConversionError",
    "JointFrameConverter",
    "LoadedDynamicsAsset",
    "Provenance",
    "UnconvertibleItem",
    "convert_joint2_angle",
    "convert_v1_to_v2",
    "load_safety_params",
    "unconvertible_items",
]
