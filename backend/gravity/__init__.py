"""WP-2B-02 — the gravity/Coriolis backend: the single `tau_grav(q)` compute point (FR-SAF-034).

Wave 2B's second sequential package (after WP-2B-01's v1->v2 converter). It computes the
gravity term the friction fit (WP-2B-07) subtracts and the momentum observer (WP-2C-01) uses as
`ĝ(q)`, from the committed v2 model's v2 inertia. Two contracts it holds:

* `tau_grav(q)` has exactly one source — this backend. `openarm_control` carries no dynamics
  model (spec 12 §2.6), so nothing downstream may assume force control is available from it.
* The gravity term is evaluated in the v2 joint convention. This package verifies the loaded
  model against WP-2B-01's frozen v2 axes and joint2 range before computing anything, because a
  v1-convention pose puts a sin<->cos error into the shoulder gravity term (spec 12 §2.6).

The public surface downstream consumes:

* `select_backend(backend_id, arm, gravity_scale)` — the FR-SAF-034 backend selector; default
  `BackendId.MUJOCO_V2` (v2 inertia via `qfrc_bias`). `Arm.RIGHT` is the WP-2B-01 reference arm.
* `GravityBackend.tau_grav(q)` and the runtime `gravity_scale` trim in `[0, 1.2]`.
* `MuJoCoV2GravityBackend` additionally exposes `tau_bias(q, q̇)` (gravity+Coriolis) and
  `tau_coriolis(q, q̇)` for the GMO's `Ĉᵀq̇` term. `URDF_KDL` is gravity-only.
* `compare_backends(q)` / `format_delta_table` — the per-joint two-backend difference table
  (acceptance ①), with `InertialParams` the pluggable inertia source that difference keys on.
"""

from __future__ import annotations

from backend.gravity.backend import Arm, BackendId, GravityBackend
from backend.gravity.compare import (
    JointGravityDelta,
    compare_backends,
    format_delta_table,
)
from backend.gravity.constants import (
    GRAVITY_SCALE_DEFAULT,
    GRAVITY_SCALE_MAX,
    GRAVITY_SCALE_MIN,
    MJCF_V2_PATH,
)
from backend.gravity.errors import GravityBackendError
from backend.gravity.model import ArmModel
from backend.gravity.mujoco_v2 import MuJoCoV2GravityBackend
from backend.gravity.selector import select_backend
from backend.gravity.urdf_kdl import InertialParams, UrdfKdlGravityBackend

__all__ = [
    "GRAVITY_SCALE_DEFAULT",
    "GRAVITY_SCALE_MAX",
    "GRAVITY_SCALE_MIN",
    "MJCF_V2_PATH",
    "Arm",
    "ArmModel",
    "BackendId",
    "GravityBackend",
    "GravityBackendError",
    "InertialParams",
    "JointGravityDelta",
    "MuJoCoV2GravityBackend",
    "UrdfKdlGravityBackend",
    "compare_backends",
    "format_delta_table",
    "select_backend",
]
