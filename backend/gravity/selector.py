"""The backend selector (FR-SAF-034): choose `MUJOCO_V2` (default) or `URDF_KDL` by id.

The default is `MUJOCO_V2` because it is the backend that uses v2 inertia (spec 12 §2.6);
`URDF_KDL` exists so acceptance ① can table the two against each other, and the FR-SAF-034
negative branch drops it and unifies on `MUJOCO_V2` if it fails to reflect v2 inertia.
"""

from __future__ import annotations

from backend.gravity.backend import Arm, BackendId, GravityBackend
from backend.gravity.constants import GRAVITY_SCALE_DEFAULT
from backend.gravity.mujoco_v2 import MuJoCoV2GravityBackend
from backend.gravity.urdf_kdl import UrdfKdlGravityBackend


def select_backend(
    backend_id: BackendId = BackendId.MUJOCO_V2,
    arm: Arm = Arm.RIGHT,
    gravity_scale: float = GRAVITY_SCALE_DEFAULT,
) -> GravityBackend:
    """Build the gravity backend named by `backend_id`, defaulting to `MUJOCO_V2`.

    Args:
        backend_id: Which backend to build; the default is the v2-inertia backend.
        arm: Which follower arm to compute for.
        gravity_scale: Initial gravity trim in `[0, 1.2]`.

    Returns:
        (GravityBackend) A ready backend for the requested arm.
    """
    if backend_id is BackendId.URDF_KDL:
        return UrdfKdlGravityBackend(arm=arm, gravity_scale=gravity_scale)
    return MuJoCoV2GravityBackend(arm=arm, gravity_scale=gravity_scale)
